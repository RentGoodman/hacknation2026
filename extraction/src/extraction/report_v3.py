from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from .v3.client import ROOT
from .v3.schemas import CATEGORIES


def _grid(rules):
    return Counter((r["jurisdiction"], r["category"]) for r in rules)


def main(old_path: str, new_dir: str) -> None:
    old = json.loads(Path(old_path).read_text())["rules"]
    nd = Path(new_dir)
    new_all = json.loads((nd / "rules.json").read_text())
    new = new_all["rules"]
    a, b = _grid(old), _grid(new)
    jurs = sorted({j for j, _ in a} | {j for j, _ in b})
    short = {c: c.split("_")[0][:5] for c in CATEGORIES}
    print("## Rules per jurisdiction x category (before -> after)\n")
    print("| Jurisdiction | " + " | ".join(short[c] for c in CATEGORIES) + " | total |")
    print("|---|" + "---|" * (len(CATEGORIES) + 1))
    for j in jurs:
        cells = [f"{a[(j, c)]}→{b[(j, c)]}" for c in CATEGORIES]
        print(f"| {j} | " + " | ".join(cells) + f" | {sum(a[(j, c)] for c in CATEGORIES)}→{sum(b[(j, c)] for c in CATEGORIES)} |")
    print(f"\nTotal: {len(old)} → {len(new)}\n")
    nf = new_all.get("no_rule_findings", [])
    print(f"## No-rule findings: {len(nf)}\n")
    for f in nf:
        print(f"- {f['jurisdiction']} / {f['category']} ({f.get('kind')}): {(f.get('reason') or f.get('finding') or '')[:120]}")
    rows = list(csv.DictReader((ROOT / "corpus_extra" / "corpus_manifest.csv").open()))
    fails = (ROOT / "corpus_extra" / "capture_failures.jsonl").read_text().splitlines()
    off = [r for r in rows if r["source_type"].startswith("official")]
    print(f"\n## Captured sources\n\nofficial ok {len(off)}, secondary ok {len(rows) - len(off)}, failed {len(fails)}\n")
    rej = json.loads((nd / "rejected.json").read_text())
    raw = json.loads((nd / "rules_raw.json").read_text())
    rep = Counter(x["how"].split("+")[0] if not x["how"].startswith("recopy") else "recopy" for x in raw["repairs"])
    print(f"## Spans\n\nrejected {len(rej)}; repaired {sum(rep.values())} ({dict(rep)})\n")
    qa = (nd / "qa_changes.jsonl").read_text().splitlines() if (nd / "qa_changes.jsonl").exists() else []
    print(f"## QA changes: {len(qa)}\n")
    print(f"## conflict_flag: before {sum(bool(r.get('conflict_flag')) for r in old)}, after "
          f"{sum(bool(r.get('conflict_flag')) for r in new)} (pipeline: {raw.get('conflict_flags')})\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
