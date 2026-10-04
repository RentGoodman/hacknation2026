from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

from . import pipeline
from .client import CACHE_DIR, ROOT


def main() -> None:
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace the canonical output with the verified offline reconstruction",
    )
    cli = parser.parse_args()

    committed = json.loads((ROOT / "out" / "rules.json").read_text(encoding="utf-8"))
    if "no_rule_findings" not in committed or not CACHE_DIR.exists():
        print("out/rules.json is not a v3 pipeline output yet; reproducibility check skipped")
        return
    seed_path = ROOT / "extraction" / "baseline" / "rules_v3_4ea86eb.jsonl"
    if not seed_path.exists():
        sys.exit(f"REPRODUCIBILITY FAILED: missing generated seed {seed_path}")
    rows = [json.loads(line) for line in seed_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    seed = {"rules": [row for row in rows if row.get("_type") != "no_rule_findings"],
            "no_rule_findings": next(row["value"] for row in rows if row.get("_type") == "no_rule_findings")}
    with tempfile.TemporaryDirectory() as d:
        args = argparse.Namespace(offline=True, docs=["DX20", "DX21"], concurrency=2,
                                  audit_path=Path(d) / "audit.jsonl")
        result = asyncio.run(pipeline.run_incremental(args, current=seed))
        if cli.write:
            pipeline.write(result, ROOT / "out")
        pipeline.write(result, Path(d))
        got = (Path(d) / "rules.json").read_bytes()
    want = (ROOT / "out" / "rules.json").read_bytes()
    if got != want:
        sys.exit("REPRODUCIBILITY FAILED: offline rerun differs from out/rules.json")
    print(f"reproducible: out/rules.json ({len(want)} bytes) rebuilt byte for byte from the cache")


if __name__ == "__main__":
    main()
