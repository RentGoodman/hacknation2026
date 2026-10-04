from . import places
import re

from .config import EXPECTED_COUNTY, STUDY_CITIES

CITY_CONFIDENCE = {"resolved": 1.0, "resolved_by_source_dataset": 0.95, "resolved_by_mod_iv_municipality": 0.9,
                   "postal_fallback": 0.8, "postal_only": None, "no_place": None, "not_geocoded": None}
MOD_IV_DATASET = "NJOGIS Parcels & MOD-IV Composite"
MOD_IV_CITIES = {"Jersey City", "Hoboken", "Newark"}

STATE_ABBR = {"06": "CA", "34": "NJ", "25": "MA"}


def resolve_cities(rows, geo):
    pts = {aid: (g["lat"], g["lon"]) for aid, g in geo.items() if g["lat"] is not None}
    hits = places.lookup(pts) if pts else {}
    out = {}
    for r in rows:
        aid = r["address_id"]
        g = geo[aid]
        if g["lat"] is None:
            out[aid] = {"city_status": "not_geocoded", "legal_city": None, "legal_short": None,
                        "place_geoid": None, "place_name": None, "outside_study_cities": False,
                        "jurisdiction_mismatch": None}
            continue
        h = hits.get(aid) or {}
        name, geoid = h.get("place_name"), h.get("place_geoid")
        if name is None:
            out[aid] = {"city_status": "no_place", "legal_city": None, "legal_short": None,
                        "place_geoid": None, "place_name": None, "outside_study_cities": False,
                        "jurisdiction_mismatch": None}
            continue
        st = STATE_ABBR.get(geoid[:2], r["state"])
        short = STUDY_CITIES.get(name)
        base = short or name.rsplit(" ", 1)[0]
        out[aid] = {"city_status": "resolved", "legal_city": f"{base}, {st}", "legal_short": short,
                    "place_geoid": geoid, "place_name": name, "outside_study_cities": short is None,
                    "jurisdiction_mismatch": r["postal_city"].strip().lower() != base.lower()}
    for c in out.values():
        c["city_confidence"] = CITY_CONFIDENCE[c["city_status"]]
        c["extra_flags"] = []
    return out


SOURCE_DATASET_CITY = {
    "Boston Property Assessment FY2026": ("Boston", "Boston, MA", "Suffolk County"),
    "DataSF wv5m-vpq2 (2025 roll)": ("San Francisco", "San Francisco, CA", "San Francisco County"),
    "Cambridge Property Database FY2026 (waa7-ibdu)": ("Cambridge", "Cambridge, MA", "Middlesex County"),
}


def fallback_city(row, c):
    postal = row["postal_city"].strip()

    def done(status, short, legal, county, flags=()):
        return {**c, "city_status": status, "legal_city": legal, "legal_short": short,
                "jurisdiction_mismatch": postal.lower() != short.lower(), "legal_city_candidate": None,
                "city_confidence": CITY_CONFIDENCE[status], "extra_flags": list(flags)}, county

    src = SOURCE_DATASET_CITY.get(row["source_dataset"])
    if src:
        return done("resolved_by_source_dataset", *src)
    study = {v.lower(): v for v in STUDY_CITIES.values()}.get(postal.lower())
    if row["source_dataset"] == MOD_IV_DATASET and study in MOD_IV_CITIES:
        st, _, county = EXPECTED_COUNTY[study]
        return done("resolved_by_mod_iv_municipality", study, f"{study}, {st}", county)
    if study and not re.match(r"^\s*\d", row["street_address"] or "") and EXPECTED_COUNTY[study][0] == row["state"]:
        st, _, county = EXPECTED_COUNTY[study]
        return done("postal_fallback", study, f"{study}, {st}", county, ["postal_fallback"])
    return {**c, "city_status": "postal_only", "legal_city": None, "legal_short": None,
            "jurisdiction_mismatch": None, "legal_city_candidate": f"{postal}, {row['state']}",
            "city_confidence": None, "extra_flags": []}, None


def sanity_check(records):
    errors = []
    for aid, b in records.items():
        short = b["_legal_short"]
        if short is None:
            continue
        st, cfips, cname = EXPECTED_COUNTY[short]
        if b["state"] != st or b["_county_fips"] != cfips:
            errors.append(f"{aid}: legal_city={b['legal_city']} but county={b['county']} ({b['_county_fips']}), expected {cname}")
    if errors:
        raise SystemExit("SANITY CHECK FAILED:\n  " + "\n  ".join(errors))
