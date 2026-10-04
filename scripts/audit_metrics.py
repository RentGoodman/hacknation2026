#!/usr/bin/env python3
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def metrics(path: Path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    unique = {}
    for row in rows:
        unique.setdefault(row["cache_key"], row)
    calls = list(unique.values())
    by_model = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                    "aggregate_seconds": 0.0})
    for row in calls:
        item = by_model[row["model"]]
        item["calls"] += 1
        item["input_tokens"] += int(row.get("input_tokens") or 0)
        item["output_tokens"] += int(row.get("output_tokens") or 0)
        item["aggregate_seconds"] += float(row.get("seconds") or 0)
    for item in by_model.values():
        item["aggregate_seconds"] = round(item["aggregate_seconds"], 2)
    return {
        "audit_rows": len(rows),
        "unique_model_calls": len(calls),
        "cache_hits": sum(bool(row["cache_hit"]) for row in rows),
        "cache_hit_rate": round(sum(bool(row["cache_hit"]) for row in rows) / len(rows), 4),
        "unique_input_tokens": sum(int(row.get("input_tokens") or 0) for row in calls),
        "unique_output_tokens": sum(int(row.get("output_tokens") or 0) for row in calls),
        "aggregate_unique_call_seconds": round(sum(float(row.get("seconds") or 0) for row in calls), 2),
        "steps": dict(sorted(Counter(row["step"] for row in calls).items())),
        "models": dict(sorted(by_model.items())),
        "billing": {
            "actual_api_usd": None,
            "note": "The recorded extraction used the Claude subscription backend. audit.jsonl has no billed_usd field; no API-dollar amount is invented."
        }
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "out/audit.jsonl")
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    result = metrics(args.input)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text)
    print(text, end="")
