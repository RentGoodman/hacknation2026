import json
from datetime import date

from .adapt_coverage import _built, is_part1
from .verdict import DEFAULT_AS_OF, ALWAYS_UNKNOWN_FACTS, _units, eval_place, eval_predicate, to_date
from .voi import missing_fact

DEFAULT_CONFIDENCE = 0.8
UNKNOWN_FACTOR = 0.5
FALLBACK_FACTOR = 0.9
INFERRED_UNITS_FACTOR = 0.9
REVIEW_BELOW = 0.7
SECONDARY_CONFIDENCE_CAP = 0.6
INFERRED_WORDS = ("inferred", "estimate", "use code")
YEAR_FACT = "year_built / certificate_of_occupancy_date"
OUTCOME = {True: "pass", False: "fail", None: "unknown"}
SUMMARY_WORD_MIN = 15
SUMMARY_WORD_MAX = 25



def _jsonable(v):
    return v.isoformat() if isinstance(v, date) else v


def _units_value(b):
    lo, hi = b.get("units_min"), b.get("units_max")
    if b.get("units") is not None:
        return b["units"]
    if lo is not None and hi is not None:
        return f"{lo} to {hi}"
    if lo is not None:
        return f"at least {lo}"
    if hi is not None:
        return f"at most {hi}"
    return None


def building_value(b, fact):
    if fact in ALWAYS_UNKNOWN_FACTS:
        return None
    if fact == "units":
        return _units_value(b)
    if fact in ("year_built", "certificate_of_occupancy_date"):
        if b.get("year_built") is not None:
            return b["year_built"]
        lo, hi = b.get("co_date_min"), b.get("co_date_max")
        return f"{lo} to {hi}" if lo and hi else None
    return _jsonable(b.get(fact))


def _check(b, fact, requirement, result):
    return {"fact": fact, "building_value": building_value(b, fact), "requirement": requirement,
            "outcome": OUTCOME[result]}


def _requirement(op, value):
    if isinstance(value, (list, tuple, set)):
        value = "[" + ", ".join(str(v) for v in value) + "]"
    return f"{op} {value}"


def _part1_checks(b, cov, as_of):
    checks = []
    basis = cov.get("construction_date_basis")
    fact = "certificate_of_occupancy_date" if basis == "certificate_of_occupancy" else "year_built"
    if cov.get("built_on_or_before"):
        checks.append(_check(b, fact, f"built on or before {cov['built_on_or_before']}",
                             _built(b, "<=", cov["built_on_or_before"], basis)[0]))
    if cov.get("built_after"):
        checks.append(_check(b, fact, f"built after {cov['built_after']}", _built(b, ">", cov["built_after"], basis)[0]))
    if cov.get("min_building_age_years") is not None:
        n, y = cov["min_building_age_years"], b.get("year_built")
        checks.append(_check(b, "year_built", f"building age at least {n} years",
                             (as_of.year - y >= n) if y is not None else None))
    if cov.get("min_units") is not None:
        checks.append(_check(b, "units", f"at least {cov['min_units']} units", _units(b, ">=", cov["min_units"])[0]))
    if cov.get("max_units") is not None:
        checks.append(_check(b, "units", f"at most {cov['max_units']} units", _units(b, "<=", cov["max_units"])[0]))
    return checks


def _dsl_checks(b, cov):
    checks = []
    for p in cov["all" if "all" in cov else "any"]:
        if isinstance(p, dict) and ({"all", "any"} & set(p)):
            checks.extend(_dsl_checks(b, p))
        elif isinstance(p, dict) and p.get("fact"):
            checks.append(_check(b, p["fact"], _requirement(p.get("op"), p.get("value")), eval_predicate(b, p)[0]))
        else:
            checks.append(_check(b, "coverage_not_machine_readable", str(p), None))
    return checks


def coverage_checks(building, rule, as_of):
    b = building or {}
    cov = (rule or {}).get("coverage_conditions")
    if cov is None or cov == {}:
        return []
    if isinstance(cov, str):
        return [_check(b, "coverage_not_machine_readable", cov.strip(), None)] if cov.strip() else []
    if is_part1(cov):
        return _part1_checks(b, cov, to_date(as_of))
    if isinstance(cov, dict) and ({"all", "any"} & set(cov)):
        return _dsl_checks(b, cov)
    return [_check(b, "coverage_not_machine_readable", "coverage not machine readable", None)]


def _fact_label(fact):
    return YEAR_FACT if fact in ("year_built", "certificate_of_occupancy_date") else fact


def facts_from_checks(checks):
    out = []
    for c in checks:
        if c["outcome"] == "unknown" and _fact_label(c["fact"]) not in out:
            out.append(_fact_label(c["fact"]))
    return out


def concise_summary(result, facts, as_of):
    if result == "applies":
        return (f"This rule applies on {as_of.isoformat()}; available property facts satisfy its building-level "
                "coverage conditions. Review the source for transaction-specific exceptions.")
    if result == "unknown":
        fact = str((facts or ["the listed building facts"])[0]).replace("_", " ")
        if len(fact.split()) > 7:
            fact = "the listed eligibility facts"
        return (f"Coverage remains unknown until {fact} is confirmed; the detailed review panel lists every "
                "missing fact and supporting source.")
    if result == "superseded":
        return ("This rule covers the building, but a more specific rule governs on the selected date. "
                "Open the details to review precedence.")
    if result == "pending":
        return ("This proposal is not law on the selected date and appears only to explain a possible future "
                "change for this building.")
    if result == "not_yet_effective":
        return ("This enacted rule takes effect after the selected date and does not yet govern this building. "
                "Open the details for timing evidence.")
    return "Review the detailed result, building facts and cited source before relying on this automated legal research output."



def source_confidence_score(rule):
    raw_confidence = (rule or {}).get("confidence")
    if raw_confidence is None:
        return DEFAULT_CONFIDENCE
    try:
        return float(raw_confidence)
    except (TypeError, ValueError):
        return DEFAULT_CONFIDENCE


def has_inferred_unit_count(building):
    count_evidence = (building.get("units_min"), building.get("units_max"))
    interval_only = building.get("units") is None and any(bound is not None for bound in count_evidence)
    count_provenance = str(building.get("units_method") or "").lower()
    inferred_provenance = any(marker in count_provenance for marker in INFERRED_WORDS)
    return interval_only or inferred_provenance


def _confidence_penalties(building, result, checks):
    if result == "unknown":
        yield UNKNOWN_FACTOR
    if building.get("city_status") != "resolved":
        yield FALLBACK_FACTOR
    if has_inferred_unit_count(building) and any(check["fact"] == "units" for check in checks):
        yield INFERRED_UNITS_FACTOR


def calculate_coverage_confidence(rule, building, result, checks):
    score = source_confidence_score(rule)
    for penalty in _confidence_penalties(building or {}, result, checks):
        score *= penalty
    return round(score, 3)


def is_secondary(rule, source_types):
    return source_types.get((rule or {}).get("source_doc_id") or "", "") != "official"



def exclusion_reason(rule, building, as_of, checks=None):
    if rule.get("status") == "failed":
        return "failed"
    from .temporal import effective_on, time_status
    temporal, _ = time_status(rule, rule.get("_annotation"), as_of)
    if temporal == "expired":
        end = rule.get("repeal_or_sunset_date") or rule.get("sunset_date") or rule.get("figure_period_end") \
            or rule.get("valid_until")
        return f"end date passed ({end})"
    checks = coverage_checks(building, rule, as_of) if checks is None else checks
    for c in checks:
        if c["outcome"] == "fail":
            return f"coverage not met: {c['fact']} {c['requirement']} (building: {c['building_value']})"
    if temporal != "in_force":
        eff = effective_on(rule)
        suffix = f" (effective {eff.isoformat()})" if eff else ""
        return f"not in force on {as_of.isoformat()}{suffix}"
    return "coverage excluded by an exemption or referenced rule condition"



def _entry(rule, b, result, explanation, d, as_of, source_types):
    checks = d.get("checks")
    if checks is None:
        checks = coverage_checks(b, rule, as_of)
    facts = d.get("missing_facts")
    if facts is None:
        facts = facts_from_checks(checks)
        if result == "unknown":
            if rule and eval_place(b, rule) == "unknown":
                facts = ["legal_city"] + [f for f in facts if f != "legal_city"]
            if not facts:
                facts = [missing_fact(explanation)]
    secondary = is_secondary(rule, source_types)
    conf = calculate_coverage_confidence(rule, b, result, checks)
    if secondary:
        conf = min(conf, SECONDARY_CONFIDENCE_CAP)
    return {"result": result, "summary": concise_summary(result, facts, as_of), "reasoning": explanation,
            "missing_facts": list(facts), "checks": checks, "confidence": conf,
            "needs_review": conf < REVIEW_BELOW or secondary}


def build_detail(lookups, buildings, rules, details, as_of, source_types=None):
    if source_types is None:
        from .prepare import source_types as load_source_types
        source_types = load_source_types()
    as_of_d = to_date(as_of)
    details = details or {}
    by_id = {r["team_rule_id"]: r for r in rules}
    addresses, review, excluded_n = {}, 0, 0
    for aid in sorted(lookups):
        b = buildings.get(aid) or {}
        dmap = details.get(aid) or {}
        out_rules = {}
        for e in lookups[aid]:
            rid = e["team_rule_id"]
            out_rules[rid] = _entry(by_id.get(rid), b, e["result"], e.get("explanation"), dmap.get(rid) or {},
                                    as_of_d, source_types)
            review += out_rules[rid]["needs_review"]
        excluded = []
        for r in rules:
            rid = r["team_rule_id"]
            if rid in out_rules or eval_place(b, r) == "no":
                continue
            d = dmap.get(rid) or {}
            reason = d.get("omit_reason") or exclusion_reason(r, b, as_of_d, d.get("checks"))
            excluded.append({"team_rule_id": rid, "reason": reason})
        excluded_n += len(excluded)
        addresses[aid] = {"rules": out_rules, "excluded": excluded}
    meta = {"as_of": as_of_d.isoformat(), "generated_by": "engine/explain.py", "address_count": len(addresses),
            "rules_evaluated": len(rules), "answers": sum(len(a["rules"]) for a in addresses.values()),
            "needs_review_answers": review, "excluded_entries": excluded_n,
            "confidence_method": {"base": f"rule confidence, {DEFAULT_CONFIDENCE} when missing",
                                  "unknown_result": UNKNOWN_FACTOR, "fallback_city": FALLBACK_FACTOR,
                                  "inferred_units_on_unit_rule": INFERRED_UNITS_FACTOR,
                                  "secondary_source_cap": SECONDARY_CONFIDENCE_CAP, "rounding": 3},
            "summary_word_target": [SUMMARY_WORD_MIN, SUMMARY_WORD_MAX],
            "needs_review_rule": f"confidence < {REVIEW_BELOW} or the source document is not official"}
    return {"as_of": as_of_d.isoformat(), "_meta": meta, "addresses": addresses}


def publicize_lookups(lookups, detail):
    addresses = detail["addresses"]
    return {
        aid: [
            {**entry, "explanation": addresses[aid]["rules"][entry["team_rule_id"]]["summary"]}
            for entry in entries
        ]
        for aid, entries in lookups.items()
    }


def write(path, data):
    with open(path, "w") as f:
        f.write(json.dumps(data, indent=2, sort_keys=False) + "\n")


def main(argv=None):
    import argparse
    from .run import ROOT, evaluation_context
    ap = argparse.ArgumentParser(description="Detail file without engine details (checks recomputed).")
    ap.add_argument("--as-of", default=DEFAULT_AS_OF)
    ap.add_argument("--out", default=str(ROOT / "out" / "lookups_detail.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    lk = json.loads((ROOT / "out" / "lookups.json").read_text())["lookups"]
    ctx = evaluation_context(fetch=False)
    data = build_detail(lk, ctx["buildings"], ctx["rules"], {}, a.as_of)
    m = data["_meta"]
    print(f"{m['address_count']} addresses, {m['answers']} answers, {m['needs_review_answers']} need review, "
          f"{m['excluded_entries']} excluded entries")
    if not a.dry_run:
        write(a.out, data)
        print(f"wrote {a.out}")
    return data


if __name__ == "__main__":
    main()
