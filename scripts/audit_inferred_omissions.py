#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def audit(root: Path = ROOT) -> dict:
    from engine.explain import coverage_checks
    from engine.run import evaluation_rules

    buildings = json.loads((root / "out" / "buildings.json").read_text())
    detail = json.loads((root / "out" / "lookups_detail.json").read_text())
    rules = {r["team_rule_id"]: r for r in evaluation_rules(fetch=False)}
    rows = []
    coverage_omissions = 0

    for address_id, address in detail["addresses"].items():
        building = buildings[address_id]
        for excluded in address.get("excluded", []):
            if excluded.get("reason") != "coverage conditions not met":
                continue
            coverage_omissions += 1
            rule_id = excluded["team_rule_id"]
            for check in coverage_checks(building, rules[rule_id], detail["as_of"]):
                if check["outcome"] != "fail":
                    continue
                fact = check["fact"]
                method = None
                exact_missing = False
                if fact == "units" and building.get("units") is None:
                    exact_missing = True
                    method = building.get("units_method")
                elif fact in ("year_built", "certificate_of_occupancy_date") and building.get("year_built") is None:
                    exact_missing = True
                    method = building.get("co_date_method") or building.get("year_built_max_method")
                if exact_missing:
                    rows.append(
                        {
                            "address_id": address_id,
                            "team_rule_id": rule_id,
                            "fact": fact,
                            "building_value": check["building_value"],
                            "requirement": check["requirement"],
                            "method": method,
                            "decision": "review",
                        }
                    )

    rows.sort(key=lambda row: (row["address_id"], row["team_rule_id"], row["fact"]))
    return {
        "as_of": detail["as_of"],
        "scope": "all 500 addresses and every evaluated rule",
        "policy": "A bound may omit a rule only when the entire possible interval fails the coverage condition.",
        "coverage_omissions_checked": coverage_omissions,
        "inferred_fact_omissions": rows,
        "counts": {
            "pairs": len(rows),
            "addresses": len({row["address_id"] for row in rows}),
            "by_fact": dict(sorted(Counter(row["fact"] for row in rows).items())),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the full deterministic report")
    args = parser.parse_args()
    report = audit()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    counts = report["counts"]
    print(
        f"Inferred-omission audit: {report['coverage_omissions_checked']} coverage omissions checked; "
        f"{counts['pairs']} inferred-fact pair(s) across {counts['addresses']} address(es)."
    )
    if report["inferred_fact_omissions"]:
        for row in report["inferred_fact_omissions"]:
            print(
                f"REVIEW {row['address_id']} {row['team_rule_id']}: {row['fact']} "
                f"{row['building_value']} vs {row['requirement']} ({row['method']})"
            )


if __name__ == "__main__":
    main()
