import json
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from .config import CACHE_DIR

SANDAG_URL = "https://geo.sandag.org/server/rest/services/Hosted/Parcels/FeatureServer/0/query"
SANDAG_DS = "SANDAG/SanGIS parcels"
NJ_URL = "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0/query"
NJ_DS = "NJOGIS Parcels & MOD-IV Composite"
NJ_SOURCE = "NJOGIS Parcels Composite NJ (MOD-IV) FeatureServer (services2.arcgis.com/XVOqAjTOJ5P6ngMu)"
NJ_METHOD = "NJ MOD-IV YR_CONSTR"
NJ_MUN = {"Newark": "NEWARK", "Hoboken": "HOBOKEN", "Jersey City": "JERSEY CITY"}
SUFFIXES = {"ST", "AVE", "AV", "BLVD", "DR", "RD", "WAY", "PL", "CT", "LN", "TER", "CIR", "PKWY", "HWY", "SQ", "TRL", "ROW", "WALK"}
DIRS = {"N", "S", "E", "W"}
STATUS = {"blocked": None}


def parse_street(street):
    toks = street.upper().replace(".", "").split()
    if len(toks) < 2 or not toks[0].isdigit():
        return None
    num, rest = toks[0], toks[1:]
    pre = rest.pop(0) if len(rest) > 1 and rest[0] in DIRS else None
    if len(rest) > 1 and rest[-1] in SUFFIXES:
        rest = rest[:-1]
    return num, " ".join(rest), pre


def sandag_where(row):
    p = parse_street(row["street_address"])
    if not p:
        return None
    num, name, pre = p
    w = f"situs_address={num} AND situs_street='{name.replace(chr(39), chr(39) * 2)}'"
    if pre:
        w += f" AND situs_pre_dir='{pre}'"
    z = re.sub(r"\D", "", row.get("zip") or "")[:5]
    if z:
        w += f" AND situs_zip LIKE '{z}%'"
    return w


def full_year(yy):
    yy = "" if yy is None else str(yy).strip()
    if yy in ("", "0", "00") or not yy.isdigit():
        return None
    y = int(yy)
    if len(yy) != 4:
        y = 2000 + y if y <= 26 else 1900 + y
    return y if y <= 2026 else None


def _fetch(row):
    aid = row["address_id"]
    path = CACHE_DIR / f"sandag_{aid}.json"
    if path.exists():
        return aid, json.loads(path.read_text())
    where = sandag_where(row)
    if where is None:
        return aid, {"where": None, "features": []}
    try:
        r = requests.get(SANDAG_URL, params={"where": where, "outFields": "apn,unitqty,year_effective", "f": "json",
                                             "returnGeometry": "false"}, timeout=30)
        r.raise_for_status()
        js = r.json()
    except (requests.RequestException, ValueError) as e:
        STATUS["blocked"] = f"SANDAG query failed ({type(e).__name__}: {e})"[:300]
        return aid, None
    if "error" in js:
        STATUS["blocked"] = f"SANDAG error: {js['error']}"[:300]
        return aid, None
    out = {"where": where, "features": [f["attributes"] for f in js.get("features", [])]}
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return aid, out


def sandag_result(resp):
    if not resp:
        return None
    parcels = [(full_year(a.get("year_effective")), a.get("apn"), a.get("unitqty")) for a in resp["features"]]
    dated = [p for p in parcels if p[0] is not None]
    if not dated:
        return None
    y = max(p[0] for p in dated)
    apns = sorted({str(p[1]) for p in parcels if p[1]})
    return {
        "year_built_max": y,
        "co_date_min": None,
        "co_date_max": f"{y}-12-31",
        "enrichment_source": "SANDAG Hosted Parcels FeatureServer (geo.sandag.org)",
        "enrichment_method": (f"year_effective (assessor effective year, upper bound on construction year) of APN {', '.join(apns)}"
                              + ("; several parcels, latest year kept" if len(dated) > 1 else "")
                              + f"; query: {resp['where']}"),
    }


def nj_where(row):
    mun = NJ_MUN.get((row.get("postal_city") or "").strip())
    street = " ".join((row.get("street_address") or "").upper().split())
    if not mun or not street:
        return None
    q = lambda v: v.replace(chr(39), chr(39) * 2)
    return f"MUN_NAME LIKE '{q(mun)}%' AND PROP_LOC='{q(street)}'"


def _nj_fetch(row):
    aid = row["address_id"]
    path = CACHE_DIR / f"njmodiv_{aid}.json"
    if path.exists():
        return aid, json.loads(path.read_text())
    where = nj_where(row)
    if where is None:
        return aid, {"where": None, "features": []}
    try:
        r = requests.get(NJ_URL, params={"where": where, "outFields": "PAMS_PIN,MUN_NAME,PROP_LOC,YR_CONSTR",
                                         "f": "json", "returnGeometry": "false"}, timeout=30)
        r.raise_for_status()
        js = r.json()
    except (requests.RequestException, ValueError) as e:
        STATUS["blocked"] = f"NJ MOD-IV query failed ({type(e).__name__}: {e})"[:300]
        return aid, None
    if "error" in js:
        STATUS["blocked"] = f"NJ MOD-IV error: {js['error']}"[:300]
        return aid, None
    feats = sorted((f["attributes"] for f in js.get("features", [])), key=lambda a: str(a.get("PAMS_PIN")))
    out = {"where": where, "features": feats}
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return aid, out


def nj_year(v):
    try:
        y = int(v)
    except (TypeError, ValueError):
        return None
    return y if 1700 <= y <= 2026 else None


def nj_result(resp):
    if not resp or not resp["features"]:
        return None
    years = {}
    for a in resp["features"]:
        y = nj_year(a.get("YR_CONSTR"))
        if y is not None:
            years.setdefault(y, []).append(str(a.get("PAMS_PIN")))
    if not years:
        return None
    if len(years) > 1:
        return {"ambiguous_year": True, "enrichment_method": "; ".join(f"{y}: PAMS_PIN {', '.join(p)}" for y, p in sorted(years.items()))
                + f"; query: {resp['where']}", "enrichment_source": NJ_SOURCE}
    (y, pins), = years.items()
    return {"year_built": y, "year_built_method": NJ_METHOD, "enrichment_source": NJ_SOURCE,
            "enrichment_method": f"{NJ_METHOD} of PAMS_PIN {', '.join(pins)}; query: {resp['where']}"}


def enrich(rows):
    todo = [r for r in rows if r["source_dataset"] == SANDAG_DS and not (r["year_built"] or "").strip()]
    nj = [r for r in rows if r["source_dataset"] == NJ_DS and not (r["year_built"] or "").strip()]
    with ThreadPoolExecutor(max_workers=6) as ex:
        resps = dict(ex.map(_fetch, todo))
        nj_resps = dict(ex.map(_nj_fetch, nj))
    out = {aid: e for aid, e in ((a, sandag_result(r)) for a, r in resps.items()) if e}
    out.update({aid: e for aid, e in ((a, nj_result(r)) for a, r in nj_resps.items()) if e})
    return out
