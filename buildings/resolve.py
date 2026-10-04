import csv
import re

from . import geocode
from .config import ADDRESSES_CSV, EXPECTED_ROWS, PRIOR_CENSUS_CSV
from .facts import zip_suspect

ID_RE = re.compile(r"^A\d{4}$")
SUFFIXES = {"ST", "STREET", "AVE", "AV", "AVENUE", "RD", "ROAD", "DR", "DRIVE", "BLVD", "PL", "PLACE", "CT",
            "COURT", "LN", "LANE", "WAY", "TER", "TERRACE", "PKWY", "HWY", "SQ", "CIR", "PARK", "PK"}
DIRECTIONS = {"N": "N", "NORTH": "N", "S": "S", "SOUTH": "S", "E": "E", "EAST": "E", "W": "W", "WEST": "W"}


def load_addresses():
    with open(ADDRESSES_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    ids = [r["address_id"] for r in rows]
    bad = [i for i in ids if not ID_RE.match(i)]
    if len(ids) != EXPECTED_ROWS or len(set(ids)) != EXPECTED_ROWS or bad:
        raise SystemExit(f"FAIL: expected {EXPECTED_ROWS} unique A#### ids, got {len(ids)} rows, "
                         f"{len(set(ids))} unique, malformed={bad}")
    return rows


def load_prior_census():
    out = {}
    if PRIOR_CENSUS_CSV.exists():
        with open(PRIOR_CENSUS_CSV, newline="") as f:
            for rec in csv.reader(f):
                if len(rec) >= 6 and rec[2] == "Match" and rec[5]:
                    lon, lat = (float(x) for x in rec[5].split(","))
                    out[rec[0]] = {"match_type": rec[3], "lat": lat, "lon": lon, "matched": rec[4]}
    return out


def first_house_number(street):
    return re.sub(r"^\s*(\d+[A-Z]?)\s*-\s*[\d.]+[A-Z]?\b", r"\1", street, flags=re.I).strip()


def normalize_street(street):
    s = re.sub(r"\b0+(\d+(ST|ND|RD|TH))\b", r"\1", street.upper())
    return re.sub(r"\bAV\b", "AVE", s)


def request_fields(r):
    z = "" if zip_suspect(r["state"], r["zip"], r.get("source_dataset")) else (r["zip"] or "")
    return first_house_number(r["street_address"]), r["postal_city"], r["state"], z


def sent_address(r, normalize=False):
    street, city, state, z = request_fields(r)
    street = normalize_street(street) if normalize else street
    return f"{street}, {city}, {state}" + (f" {z}" if z else "")


def _street_key(street):
    toks = re.sub(r"[.,#]", " ", (street or "").upper()).split()
    if not toks or not re.match(r"^\d", toks[0]):
        return None, tuple(toks)
    num = toks[0]
    core = []
    for t in toks[1:]:
        t = re.sub(r"^0+(\d)", r"\1", t)
        if t in SUFFIXES:
            continue
        core.append(DIRECTIONS.get(t, t))
    return num, tuple(core)


def same_address(r, matched):
    parts = [p.strip() for p in (matched or "").split(",")]
    if len(parts) < 4:
        return False
    m_street, m_state = parts[0], parts[-2]
    s_num, s_core = _street_key(request_fields(r)[0])
    m_num, m_core = _street_key(m_street)
    return s_num is not None and s_num == m_num and s_core == m_core and m_state.upper() == r["state"].upper()


REJECTED_MATCHES = []


def source_house_numbers(street):
    m = re.match(r"^\s*(\d+(?:\.\d+)?)([A-Z]?)\s*(?:(-|&|and|/)\s*(\d+(?:\.\d+)?)([A-Z]?))?\b", (street or "").upper())
    if not m:
        return set(), None
    a, sa, sep, b, sb = m.groups()
    nums = {str(int(float(a))) + sa} | ({str(int(float(b))) + (sb or "")} if b else set())
    rng = (float(a), float(b)) if b and sep == "-" else None
    return nums, rng


def house_number_mismatch(r, matched):
    m_num = _street_key((matched or "").split(",")[0])[0]
    m_num = m_num.rstrip("-") if m_num else m_num
    nums, rng = source_house_numbers(r["street_address"])
    if not nums:
        return None
    if m_num in nums or (rng and m_num and m_num.isdigit() and rng[0] <= int(m_num) <= rng[1]):
        return None
    return f"house number {'/'.join(sorted(nums))} -> {m_num or 'none'}"


def geocode_all(rows, refresh=False):
    REJECTED_MATCHES.clear()
    batch = geocode.batch_geographies(
        [(r["address_id"], *request_fields(r)) for r in rows], refresh=refresh)
    prior = load_prior_census()

    def batch_ok(r):
        b = batch.get(r["address_id"], {})
        return b.get("match_status") == "Match" and not house_number_mismatch(r, b.get("matched_address"))

    retry = [r for r in rows if not batch_ok(r)]
    one = geocode.parallel(geocode.oneline, [(r["address_id"], sent_address(r)) for r in retry])
    again = [r for r in retry if not ((one.get(r["address_id"]) or {}).get("result") or {}).get("addressMatches")
             and sent_address(r, normalize=True) != sent_address(r).upper()]
    for aid, res in geocode.parallel(geocode.oneline, [(r["address_id"], sent_address(r, normalize=True))
                                                       for r in again]).items():
        if ((res or {}).get("result") or {}).get("addressMatches"):
            one[aid] = res

    geo = {}
    for r in rows:
        aid = r["address_id"]
        b = batch.get(aid, {})
        g = {"lat": None, "lon": None, "status": "failed", "normalized_address": None, "source": None,
             "batch_match_status": b.get("match_status") or "missing", "batch_match_type": b.get("match_type"),
             "ambiguous": b.get("match_status") == "Tie", "county_fips": b.get("county_fips")}

        def take(lat, lon, matched, source, exact=False):
            g.update(lat=lat, lon=lon, normalized_address=matched, source=source,
                     status="exact" if exact else ("approximate" if same_address(r, matched) else "manual_review"))

        def ok(matched, source, sent):
            reason = house_number_mismatch(r, matched)
            if reason:
                REJECTED_MATCHES.append({"address_id": aid, "sent_address": sent, "matched_address": matched,
                                         "source": source, "reason": reason})
            return reason is None

        if b.get("match_status") == "Match" and ok(b["matched_address"], "census_batch_geographies",
                                                    ", ".join(x for x in request_fields(r) if x)):
            take(b["lat"], b["lon"], b["matched_address"], "census_batch_geographies", exact=b["match_type"] == "Exact")
        else:
            if b.get("match_status") == "Match":
                g["batch_match_status"] = "Rejected"
            matches = ((one.get(aid) or {}).get("result") or {}).get("addressMatches") or []
            if len(matches) == 1 and ok(matches[0]["matchedAddress"], "census_onelineaddress", sent_address(r)):
                m = matches[0]
                take(m["coordinates"]["y"], m["coordinates"]["x"], m["matchedAddress"], "census_onelineaddress")
            elif aid in prior and ok(prior[aid]["matched"], "mockup_census_results_csv", sent_address(r)):
                p = prior[aid]
                take(p["lat"], p["lon"], p["matched"], "mockup_census_results_csv", exact=p["match_type"] == "Exact")
            if len(matches) > 1:
                g["ambiguous"] = True
            if g["lat"] is None and g["ambiguous"]:
                g.update(status="manual_review", source="census_onelineaddress")
        geo[aid] = g

    need = [(aid, g["lat"], g["lon"]) for aid, g in geo.items() if g["lat"] is not None]
    for aid, res in geocode.parallel(geocode.coordinates, need).items():
        c = geocode.parse_geographies((res.get("result") or {}).get("geographies") or {})
        geo[aid]["county"], geo[aid]["county_fips"] = c["county"], c["county_fips"] or geo[aid]["county_fips"]
    for g in geo.values():
        g.setdefault("county", None)
    return geo
