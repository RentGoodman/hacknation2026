import re
from collections import Counter, defaultdict

HDR = "| id | input address | postal city | legal city | county | status | normalized address |\n|---|---|---|---|---|---|---|"


def _row(b):
    return (f"| {b['address_id']} | {b['input_address']} | {b['postal_city']} | {b['legal_city'] or '-'} | "
            f"{b['county'] or '-'} | {b['geocode_status']} | {b['normalized_address'] or '-'} |")


def build_report(records, enrich_blocked=None):
    bs = [records[k] for k in sorted(records)]
    L = ["# Buildings report (Part 2)", "", f"Rows: {len(bs)} in, {len(bs)} out (all CSV ids present once).", ""]

    def table(title, counter, head):
        L.extend(["", f"## {title}", "", f"| {head} | count |", "|---|---|"])
        L.extend(f"| {k} | {v} |" for k, v in sorted(counter.items(), key=lambda kv: str(kv[0])))

    table("Counts per legal city", Counter(b["legal_city"] or "(unresolved)" for b in bs), "legal city")
    table("Counts per legal city and county",
          Counter(f"{b['legal_city'] or '(unresolved)'} / {b['county'] or '(unknown)'}" for b in bs), "legal city / county")
    table("City status", Counter(b["city_status"] for b in bs), "city_status")
    table("Geocode status", Counter(b["geocode_status"] for b in bs), "status")
    table("Flags", Counter(f for b in bs for f in b["flags"]), "flag")

    def section(title, pred, note=""):
        sel = [b for b in bs if pred(b)]
        L.extend(["", f"## {title} ({len(sel)})", ""] + ([note, ""] if note else []))
        L.extend([HDR] + [_row(b) for b in sel] if sel else ["None."])

    section("Jurisdiction mismatches (postal city differs from legal city)", lambda b: b["jurisdiction_mismatch"])
    section("Failed", lambda b: b["geocode_status"] == "failed")
    section("Manual review", lambda b: b["geocode_status"] == "manual_review",
            "Approximate match whose matched city or state disagrees with the input, or several candidates (ambiguous_match).")
    section("Legal city unresolved", lambda b: b["legal_city"] is None,
            "city_status postal_only, no_place or not_geocoded.")
    section("City resolved by source dataset scope", lambda b: b["city_status"] == "resolved_by_source_dataset",
            "Point lookup failed; single-city source dataset (Boston, DataSF, Cambridge) gives the city.")
    section("Postal city only (legal city unknown)", lambda b: b["city_status"] == "postal_only",
            "Multi-city source dataset; legal_city stays null, legal_city_candidate holds the postal city. "
            "Part 3 must answer unknown for city-level rules.")
    section("Suspect ZIP (not sent to the Census)", lambda b: b["zip_suspect"])
    section("Outside the 9 study cities", lambda b: "outside_study_cities" in b["flags"])
    section("Unincorporated (geocoded, no incorporated place)", lambda b: b["unincorporated"] is True)

    enriched = Counter(b["legal_city"] or "(unresolved)" for b in bs
                       if b["year_built"] is None and b["year_built_max"] is not None)
    L.extend(["", "## Public-source enrichment (buildings/enrich.py)", "",
              f"SANDAG parcels: {sum(enriched.values())} rows without year_built got year_built_max / co_date_max "
              f"({sum(1 for b in bs if b['year_built'] is None and (b['year_built_max'] or 9999) <= 2010)} with a year <= 2010). "
              "Berkeley: no public source with year built or unit count (see buildings/README.md)."])
    if enrich_blocked:
        L.append(f"Enrichment request failed: {enrich_blocked}")
    L.extend(["", "## Missing facts per legal city", "",
              "owner_type is missing on every row; certificate_of_occupancy_date is missing when year_built is unknown.", "",
              "| legal city | rows | year_built | units | property_type |", "|---|---|---|---|---|"])
    agg = defaultdict(Counter)
    for b in bs:
        a = agg[b["legal_city"] or "(unresolved)"]
        a["rows"] += 1
        a.update(m for m in b["missing_facts"] if m in ("year_built", "units", "property_type"))
    for k in sorted(agg):
        a = agg[k]
        L.append(f"| {k} | {a['rows']} | {a['year_built']} | {a['units']} | {a['property_type']} |")

    L += ["", "## Unit counts: provenance", "", "| units_method | buildings |", "|---|---|"]
    meth = Counter(re.sub(r" \(.*", "", b.get("units_method") or "") for b in bs)
    L += [f"| {k} | {v} |" for k, v in sorted(meth.items())]
    exc = [b for b in bs if b["units"] is None and b.get("units_min") is None]
    L += ["", f"Buildings without units and without a lower bound: {len(exc)}" + (": " + ", ".join(
        f"{b['address_id']} ({b['use_description']})" for b in exc) if exc else " (none).")]
    conf = [b for b in bs if "units_conflict" in b["flags"]]
    L += ["", f"### Unit conflicts ({len(conf)})", "", "Contradicting number not used; interval or explicit count kept.", "",
          "| id | use_description | units_raw | interval | method |", "|---|---|---|---|---|"]
    L += [f"| {b['address_id']} | {b['use_description']} | {b.get('units_raw')} | {b.get('units_min')}..{b.get('units_max')} | "
          f"{b.get('units_method')} |" for b in conf]
    from .resolve import REJECTED_MATCHES
    L += ["", f"## Census matches rejected for house number ({len(REJECTED_MATCHES)})", "",
          "| id | source | sent | matched | reason |", "|---|---|---|---|---|"]
    L += [f"| {m['address_id']} | {m['source']} | {m['sent_address']} | {m['matched_address']} | {m['reason']} |"
          for m in REJECTED_MATCHES] or ["None."]

    thr = [b for b in bs if b["threshold_year_case"]]
    L.extend(["", f"## Threshold year cases ({len(thr)})", "",
              "LA with year_built 1978 or SF with 1979: certificate of occupancy date unknown, Part 3 must answer unknown.", ""])
    L.extend(["| id | input address | legal city | year_built |", "|---|---|---|---|"] +
             [f"| {b['address_id']} | {b['input_address']} | {b['legal_city']} | {b['year_built']} |" for b in thr]
             if thr else ["None."])
    return "\n".join(L) + "\n"
