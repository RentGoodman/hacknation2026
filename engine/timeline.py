import argparse
import json
import sys
from datetime import date

from engine.run import evaluation_context
from engine.temporal import build_rule_timeline

DEFAULT_START = "2024-01-01"
DEFAULT_END = "2028-12-31"


def _iso(s, name):
    try:
        if len(s) != 10:
            raise ValueError
        return date.fromisoformat(s).isoformat()
    except ValueError:
        print(f"error: --{name} must be YYYY-MM-DD, got {s!r}", file=sys.stderr)
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dates on which the rule results for one building change.")
    ap.add_argument("--address", required=True, help="address_id, e.g. A0001")
    ap.add_argument("--start", default=DEFAULT_START, help="YYYY-MM-DD (default %(default)s)")
    ap.add_argument("--end", default=DEFAULT_END, help="YYYY-MM-DD (default %(default)s)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    start, end = _iso(a.start, "start"), _iso(a.end, "end")
    if start is None or end is None:
        return 2
    if start > end:
        print(f"error: --start {start} is after --end {end}", file=sys.stderr)
        return 2

    ctx = evaluation_context(fetch=False)
    b = ctx["buildings"].get(a.address)
    if b is None:
        print(f"error: unknown address id {a.address!r} (not in out/buildings.json)", file=sys.stderr)
        return 2
    tl = build_rule_timeline(b, ctx["rules"], start, end)

    if a.json:
        print(json.dumps({"address_id": a.address, "start": start, "end": end, "timeline": tl}, indent=2))
        return 0

    print(f"Address:  {a.address}  {b.get('address', '')}".rstrip())
    print(f"Window:   {start} to {end}")
    print()
    for step in tl:
        if step.get("initial"):
            print(f"{step['date']}  state at start")
            for c in step["changes"]:
                print(f"  {c['team_rule_id']:<12} {c['after']}")
        else:
            print(f"{step['date']}  changes")
            for c in step["changes"]:
                print(f"  {c['team_rule_id']:<12} {c['before']} -> {c['after']}")
    if len(tl) == 1:
        print("\n(no result changes in the window)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
