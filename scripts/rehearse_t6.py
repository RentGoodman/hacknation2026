#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="t6-rehearsal-") as tmp:
        tmp = Path(tmp)
        rules_out, summary_out = tmp / "rules.json", tmp / "summary.json"
        command = [
            sys.executable, "-m", "engine.ingest_new", str(ROOT / "engine/fixtures/fake_cambridge_ordinance.txt"),
            "--jurisdiction", "Cambridge, MA", "--effective", "2027-01-01", "--extractor", "deterministic",
            "--rules-out", str(rules_out), "--summary-out", str(summary_out), "--dry-run",
        ]
        started = time.perf_counter()
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        elapsed = time.perf_counter() - started
        result = json.loads(summary_out.read_text())["summary"]
    expected = json.loads((ROOT / "engine/fixtures/t6_rehearsal.json").read_text())["summary"]
    fields = ("new_rule_ids", "effective_date", "affected", "applies", "unknown", "conflicts", "by_city")
    mismatches = [f for f in fields if result.get(f) != expected.get(f)]
    if mismatches:
        raise SystemExit("T6 rehearsal differs from the accepted fixture: " + ", ".join(mismatches))
    print(f"T6 PASS in {elapsed:.2f}s — {len(result['new_rule_ids'])} rules, {result['affected']} affected, "
          f"{result['unknown']} unknown, {result['conflicts']} conflicts")
    print("Dry run: out/rules.json and out/changes.json were not modified.")


if __name__ == "__main__":
    main()
