import argparse
import json
import re
import sys
from datetime import date

from .rules import ROOT, load_buildings, load_rules

RESULTS = {"applies", "unknown", "superseded", "not_yet_effective", "pending"}
IN_FORCE = {"applies", "unknown", "superseded"}
RULE_ID = re.compile(r"\((r-\d{4})\)")
T5_CITIES = ("Boston, MA", "Cambridge, MA")


def day(s):
    if s is None:
        return None
    y, m, d = (str(s).split("-") + ["1", "1"])[:3]
    return date(int(y), int(m), int(d))


def place(rule):
    j = rule["jurisdiction"].strip()
    return (j.rsplit(",", 1)[1].strip(), j) if "," in j else (j, None)


def check_lookups(L, buildings, rules, as_of, annotations=None, detail=None):
    if annotations is None:
        from .precedence import load_annotations
        annotations, _ = load_annotations(rules, rules)
    bad, warn = [], []
    by_id = {r["team_rule_id"]: r for r in rules}
    from .changes import petition_25_21_ids
    petition = petition_25_21_ids(rules)
    as_of = day(as_of)
    if set(L) != set(buildings):
        bad.append(f"addresses: {len(L)} in lookups, {len(buildings)} buildings; "
                   f"missing {sorted(set(buildings) - set(L))[:5]}, extra {sorted(set(L) - set(buildings))[:5]}")
    for aid, entries in L.items():
        b = buildings.get(aid, {})
        seen = {e["team_rule_id"]: e for e in entries}
        if len(seen) != len(entries):
            bad.append(f"{aid}: a rule is listed twice")
        for e in entries:
            rid, res = e["team_rule_id"], e["result"]

            def fail(msg):
                bad.append(f"{aid} {rid}: {msg} (got {res})")

            rule = by_id.get(rid)
            if rule is None:
                fail("rule id not in rules.json")
                continue
            if res not in RESULTS:
                fail("result is not one of " + ", ".join(sorted(RESULTS)))
            if not (e.get("explanation") or "").strip():
                fail("no explanation")
            if not isinstance(e.get("conflict_flag"), bool):
                fail("conflict_flag is not true/false")

            state, city = place(rule)
            if b.get("state") != state:
                fail(f"rule for {rule['jurisdiction']} reported in {b.get('state')}")
            elif city:
                legal = b.get("legal_city")
                if legal and legal != city:
                    fail(f"city rule for {city} reported for a building in {legal}")
                if not legal and res in ("applies", "superseded"):
                    fail(f"city rule treated as certain although the legal city is unresolved "
                         f"(city_status {b.get('city_status')})")

            status = rule.get("status")
            if status == "failed":
                fail("failed rule was reported")
            if (status == "pending") != (res == "pending"):
                fail(f"result does not match status {status}")

            from .coverage_v3 import first_effective
            eff = first_effective(rule) or day(rule.get("effective_date"))
            if res == "not_yet_effective" and not ((eff and eff > as_of) or (eff is None and status == "not_yet_effective")):
                fail(f"not_yet_effective but effective date {eff or rule.get('effective_date')} is not after {as_of}")
            if res in IN_FORCE and eff and eff > as_of:
                fail(f"treated as in force before its effective date {rule.get('effective_date')}")

            if res == "unknown" and len(e["explanation"]) < 40:
                fail("unknown without saying what is missing")
            if res == "superseded":
                reasoning = (((detail or {}).get(aid) or {}).get("rules", {}).get(rid, {}).get("reasoning")
                             or e["explanation"])
                winners = [w for w in RULE_ID.findall(reasoning) if w != rid]
                if not winners:
                    fail("superseded without naming the rule that governs")
                elif not any(w in seen for w in winners):
                    fail(f"superseded by {winners}, which is not listed at this address")
                elif not any(seen[w]["result"] in ("applies", "superseded") for w in winners if w in seen):
                    from .precedence import complementary
                    winner_rules = [by_id[w] for w in winners if w in by_id and w in seen]
                    if len(winner_rules) < 2 or not complementary(winner_rules, annotations):
                        warn.append(f"{aid} {rid}: superseded by {winners}, but that rule is only "
                                    f"{'/'.join(seen[w]['result'] for w in winners if w in seen)} here, "
                                    "so this rule may still govern")

        if (b.get("legal_city") or b.get("legal_city_candidate")) in T5_CITIES:
            for e in entries:
                if e["team_rule_id"] in petition:
                    bad.append(f"{aid} {e['team_rule_id']}: petition 25-21 reported in "
                               f"{b.get('legal_city')} (T5)")
    return bad, warn


def check_changes(C, buildings, tests):
    bad = []
    for t in tests:
        tid = t["test_id"]
        if tid not in C:
            bad.append(f"changes.json: {tid} missing")
            continue
        c = C[tid]
        for key in ("affected_address_ids", "conflict_flag_address_ids"):
            ids = c.get(key, [])
            unknown = sorted(set(ids) - set(buildings))
            if unknown:
                bad.append(f"changes.json {tid}: {key} has ids not in buildings {unknown[:5]}")
            if len(set(ids)) != len(ids):
                bad.append(f"changes.json {tid}: {key} has duplicates")
        if not (c.get("notes") or "").strip():
            bad.append(f"changes.json {tid}: no notes")
        if t.get("type") == "negative" and c.get("affected_address_ids"):
            bad.append(f"changes.json {tid}: negative test should affect no address, got {len(c['affected_address_ids'])}")
    return bad


def fresh_lookups(buildings, as_of):
    from .run import evaluation_rules
    from .verdict import lookups
    return lookups(buildings, evaluation_rules(), as_of)


def report(label, bad, warn=()):
    print(f"{label}: {len(bad)} violations, {len(warn)} warnings")
    for kind, lines in (("FAIL", bad), ("warn", warn)):
        for line in lines[:10]:
            print(f"  {kind} {line}")
        if len(lines) > 10:
            print(f"  {kind} ... and {len(lines) - 10} more")
    return bool(bad)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", nargs="*", default=[], help="extra dates to recompute and check (YYYY-MM-DD)")
    a = ap.parse_args(argv)

    buildings = load_buildings()
    rules, source, is_fixture = load_rules(fetch=False)
    from .precedence import load_annotations
    annotations, _ = load_annotations(rules, rules)
    print(f"rules: {source} ({len(rules)} rules); buildings: {len(buildings)}"
          + ("  WARNING: TEST ONLY fixture" if is_fixture else ""))

    failed = False
    lk = json.loads((ROOT / "out" / "lookups.json").read_text())
    detail_path = ROOT / "out" / "lookups_detail.json"
    detail = json.loads(detail_path.read_text()).get("addresses", {}) if detail_path.exists() else {}
    failed |= report(f"out/lookups.json as of {lk['as_of']}",
                     *check_lookups(lk["lookups"], buildings, rules, lk["as_of"], annotations, detail))

    tests = json.loads((ROOT / "starter pack" / "dev" / "change_tests.json").read_text())
    C = json.loads((ROOT / "out" / "changes.json").read_text())
    failed |= report("out/changes.json", check_changes(C, buildings, tests))

    for d in a.as_of:
        failed |= report(f"recomputed as of {d}",
                         *check_lookups(fresh_lookups(buildings, d), buildings, rules, d, annotations))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
