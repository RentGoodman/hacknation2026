from __future__ import annotations

import re
from datetime import datetime

from .merge import load_all_docs, load_rules_file, save_rules_file
from .spans import SpanLocator

RULES = {"r-0123": "98.1103(a)", "r-0124": "98.1103(b)"}
SPANS = {
    "r-0123": "It is unlawful for a person to sell, license, or otherwise provide an algorithmic device to a landlord.",
    "r-0124": "It is unlawful for a landlord to use an algorithmic device to set rental rates or occupancy levels for "
    "residential rental property.",
}
HISTORY = re.compile(
    r"\(“Use and Sale of Algorithmic Devices Prohibited” added (\d{1,2}-\d{1,2}-\d{4}) by\s+(O-\d+ N\.S\.); "
    r"effective (\d{1,2}-\d{1,2}-\d{4})\.\)"
)


def _iso(mdy: str) -> str:
    return datetime.strptime(mdy, "%m-%d-%Y").date().isoformat()


def main() -> None:
    doc = next(d for d in load_all_docs() if d.doc_id == "DX05")
    m = HISTORY.search(doc.text)
    if not m:
        raise SystemExit("DX05 does not state adoption of § 98.1103; r-0123/r-0124 unchanged")
    added, ordinance, effective = _iso(m.group(1)), m.group(2), _iso(m.group(3))
    locator = SpanLocator(doc.text)
    data = load_rules_file()
    for r in data["rules"]:
        section = RULES.get(r["team_rule_id"])
        if not section:
            continue
        exact = locator.locate(SPANS[r["team_rule_id"]])
        if exact is None or locator.locate(r["quoted_span"]) is None:
            raise SystemExit(f"{r['team_rule_id']}: quoted text not found in DX05; unchanged")
        r.update(
            status="in_force",
            effective_date=effective,
            title=r["title"].replace("proposed ", ""),
            citation=f"San Diego Municipal Code § {section} ({ordinance}, adopted {added}, effective {effective})",
            source_doc_id="DX05",
            source_url=doc.url,
            quoted_span=exact,
            confidence=max(r.get("confidence") or 0, 0.9),
            conflict_flag=False,
            conflict_note=None,
        )
        print(f"{r['team_rule_id']}: in_force from {effective} on DX05 § {section}")
    save_rules_file(data)


if __name__ == "__main__":
    main()
