import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from .config import EXPECTED_ROWS, OUT_DIR, OUT_JSON, OUT_REPORT
from .facts import facts, threshold_year_case
from .config import EXPECTED_COUNTY
from .jurisdiction import fallback_city, resolve_cities, sanity_check
from .enrich import STATUS as ENRICH_STATUS, enrich
from .report import build_report
from .resolve import geocode_all, load_addresses, sent_address

FIELDS = ["address_id", "state", "legal_city", "legal_city_candidate", "city_status", "city_confidence", "place_geoid", "county", "lat", "lon",
          "year_built", "units", "units_raw", "units_min", "units_max", "units_method", "use_code", "use_description", "source_dataset", "property_type",
          "missing_facts", "threshold_year_case", "year_built_max", "year_built_max_method", "co_date_min", "co_date_max", "co_date_method",
          "subsidized", "subsidized_source", "elderly_housing", "elderly_housing_source", "tenancy_in_common", "tenancy_in_common_source", "input_address", "postal_city", "zip", "zip_suspect",
          "sent_address", "normalized_address", "geocode_status", "batch_match_status", "batch_match_type",
          "jurisdiction_mismatch", "unincorporated", "flags", "geocoded_at"]


def build(refresh=False):
    rows = load_addresses()
    geo = geocode_all(rows, refresh=refresh)
    from .resolve import REJECTED_MATCHES
    rejected = list(REJECTED_MATCHES)
    for m in rejected:
        print(f"REJECTED {m['address_id']} [{m['source']}] sent={m['sent_address']!r} matched={m['matched_address']!r} ({m['reason']})")
    cities = resolve_cities(rows, geo)
    extra = enrich(rows)
    if ENRICH_STATUS["blocked"]:
        print(f"ENRICHMENT BLOCKED: {ENRICH_STATUS['blocked']}")
    stamp = Path(__file__).resolve().parent / "cache" / "geocoded_at.txt"
    if refresh or not stamp.exists():
        stamp.write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")
    now = stamp.read_text().strip()
    records = {}
    for r in rows:
        aid = r["address_id"]
        g, f, c = geo[aid], facts(r, extra.get(aid)), {**cities[aid], "legal_city_candidate": None}
        county, county_fips = g["county"], g["county_fips"]
        if c["city_status"] != "resolved":
            c, src_county = fallback_city(r, c)
            if src_county:
                county, county_fips = src_county, EXPECTED_COUNTY[c["legal_short"]][1]
        thr = threshold_year_case(f["year_built"], c["legal_city"])
        flags = [name for name, on in (
            ("geocode_failed", g["status"] == "failed"),
            ("manual_review", g["status"] == "manual_review"),
            ("approximate_match", g["status"] == "approximate"),
            ("ambiguous_match", g["ambiguous"]),
            ("zip_suspect", f["zip_suspect"]),
            ("not_geocoded", c["city_status"] == "not_geocoded"),
            ("no_place", c["city_status"] == "no_place"),
            ("city_from_source_dataset", c["city_status"] == "resolved_by_source_dataset"),
            ("postal_only", c["city_status"] == "postal_only"),
            ("city_from_mod_iv_municipality", c["city_status"] == "resolved_by_mod_iv_municipality"),
            ("units_conflict", f["units_conflict"]),
            ("outside_study_cities", c["outside_study_cities"]),
            ("jurisdiction_mismatch", c["jurisdiction_mismatch"] is True),
            ("threshold_year_case", thr),
            ("ambiguous_year", f["ambiguous_year"]),
        ) if on]
        rec = {
            "address_id": aid, "state": r["state"], "legal_city": c["legal_city"],
            "legal_city_candidate": c["legal_city_candidate"], "city_status": c["city_status"],
            "city_confidence": c.get("city_confidence"),
            "place_geoid": c["place_geoid"], "county": county, "lat": g["lat"], "lon": g["lon"],
            **{k: f[k] for k in ("year_built", "units", "units_raw", "units_min", "units_max", "units_method", "use_code", "use_description",
                                 "source_dataset", "property_type", "missing_facts")},
            "threshold_year_case": thr, **year_dates(f, extra.get(aid)),
            **{k: f[k] for k in ("subsidized", "subsidized_source", "elderly_housing", "elderly_housing_source",
                                 "tenancy_in_common", "tenancy_in_common_source")},
            "input_address": input_address(r), "postal_city": r["postal_city"],
            "zip": r["zip"] or None, "zip_suspect": f["zip_suspect"], "sent_address": sent_address(r),
            "normalized_address": g["normalized_address"], "geocode_status": g["status"],
            "batch_match_status": g["batch_match_status"], "batch_match_type": g["batch_match_type"],
            "jurisdiction_mismatch": c["jurisdiction_mismatch"],
            "unincorporated": {"no_place": True, "resolved": False, "resolved_by_source_dataset": False,
                               "resolved_by_mod_iv_municipality": False, "postal_fallback": False}.get(c["city_status"]),
            "flags": flags + [x for x in c.get("extra_flags", []) if x not in flags], "geocoded_at": now if g["source"] else None,
        }
        assert list(rec) == FIELDS, aid
        rec["_legal_short"], rec["_county_fips"] = c["legal_short"], county_fips
        records[aid] = rec
    sanity_check(records)
    csv_ids = [r["address_id"] for r in rows]
    if len(records) != EXPECTED_ROWS or list(records) != csv_ids:
        raise SystemExit(f"FAIL: {len(records)} records, ids differ from CSV: {set(records) ^ set(csv_ids)}")
    return records


def year_dates(f, e):
    if f["year_built"] is not None:
        return {"year_built_max": f["year_built"], "year_built_max_method": f["year_built_method"],
                **{k: f[k] for k in ("co_date_min", "co_date_max", "co_date_method")}}
    if e and e.get("year_built_max") is not None:
        m = f"{e['enrichment_method']} [{e['enrichment_source']}]"
        return {"year_built_max": e["year_built_max"], "year_built_max_method": m,
                "co_date_min": None, "co_date_max": e["co_date_max"], "co_date_method": "upper bound only: " + m}
    return {"year_built_max": None, "year_built_max_method": None, "co_date_min": None, "co_date_max": None, "co_date_method": None}


def input_address(r):
    s = f"{r['street_address']}, {r['postal_city']}, {r['state']}"
    return f"{s} {r['zip']}" if r["zip"] else s


def validate(clean):
    import jsonschema
    schema = json.loads((Path(__file__).resolve().parent / "schema" / "buildings.schema.json").read_text())
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(clean), key=lambda e: list(e.path))
    if errors:
        raise SystemExit("SCHEMA CHECK FAILED:\n  " + "\n  ".join(f"{list(e.path)}: {e.message}" for e in errors[:20]))


def main():
    records = build(refresh="--refresh" in sys.argv)
    OUT_DIR.mkdir(exist_ok=True)
    report = build_report(records, ENRICH_STATUS["blocked"])
    clean = {aid: {k: v for k, v in rec.items() if not k.startswith("_")} for aid, rec in sorted(records.items())}
    validate(clean)
    OUT_JSON.write_text(json.dumps(clean, indent=2) + "\n")
    OUT_REPORT.write_text(report)
    print(f"wrote {OUT_JSON} ({len(clean)} buildings) and {OUT_REPORT}")


if __name__ == "__main__":
    main()
