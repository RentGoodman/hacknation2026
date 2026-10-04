import argparse
import json
import sys
from datetime import date

from engine.run import evaluation_rules, presented_lookups
from engine.rules import load_buildings, load_rules
from engine.verdict import DEFAULT_AS_OF


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rule lookups for one building.")
    ap.add_argument("--address", required=True, help="address_id, e.g. A0001")
    ap.add_argument("--as-of", default=DEFAULT_AS_OF, help="YYYY-MM-DD (default %(default)s)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        if len(a.as_of) != 10:
            raise ValueError
        date.fromisoformat(a.as_of)
    except ValueError:
        print(f"error: --as-of must be YYYY-MM-DD, got {a.as_of!r}", file=sys.stderr)
        return 2

    buildings = load_buildings()
    b = buildings.get(a.address)
    if b is None:
        print(f"error: unknown address id {a.address!r} (not in out/buildings.json)", file=sys.stderr)
        return 2

    _, source, is_fixture = load_rules()
    rules = evaluation_rules()
    entries = presented_lookups({a.address: b}, rules, a.as_of)[0][a.address]

    if a.json:
        print(json.dumps({"address_id": a.address, "as_of": a.as_of, "rules_source": source,
                          "lookups": entries}, indent=2))
        return 0

    city = b.get("legal_city") or (f"unresolved (city_status={b.get('city_status')}, "
                                   f"candidate={b.get('legal_city_candidate')})")
    print(f"Address:  {a.address}  {b.get('address', '')}".rstrip())
    print(f"City:     {city}")
    print(f"State:    {b.get('state')}")
    print(f"As of:    {a.as_of}")
    print(f"Rules:    {source}")
    if is_fixture:
        print("!" * 70)
        print("WARNING: TEST ONLY fixture rules. Part 1 rules.json not found.")
        print("!" * 70)
    print()
    if not entries:
        print("(no rules match this building)")
    for e in entries:
        flag = "[CONFLICT]" if e.get("conflict_flag") else ""
        print(f"{e['result']:<18} {e['team_rule_id']:<12} {flag:<10} {e['explanation']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
