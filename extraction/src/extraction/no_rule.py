from __future__ import annotations

from typing import Any

from .corpus import Document
from .merge import load_all_docs
from .spans import SpanLocator

C40P_SPAN = (
    "No city or town may enact, maintain or enforce rent control of any kind, except that any city or town that "
    "accepts this chapter may adopt rent control"
)
C40P_CITIES = ["Boston, MA", "Cambridge, MA"]


def add_finding(
    data: dict[str, Any], jurisdiction: str, category: str, citation: str, quoted_span: str, reason: str, doc: Document
) -> bool:
    exact = SpanLocator(doc.text).locate(quoted_span)
    if exact is None:
        raise ValueError(f"{doc.doc_id}: no-rule quote not found verbatim")
    findings = data.setdefault("no_rule_findings", [])
    if any(f["jurisdiction"] == jurisdiction and f["category"] == category and f["quoted_span"] == exact for f in findings):
        return False
    findings.append(
        {
            "jurisdiction": jurisdiction,
            "category": category,
            "citation": citation,
            "quoted_span": exact,
            "reason": reason,
            "source_doc_id": doc.doc_id,
            "source_url": doc.url,
        }
    )
    findings.sort(key=lambda f: (f["jurisdiction"], f["category"], f["source_doc_id"]))
    return True


def add_static_findings(data: dict[str, Any]) -> None:
    d048 = next(d for d in load_all_docs() if d.doc_id == "D048")
    for city in C40P_CITIES:
        add_finding(
            data,
            city,
            "rent_increase_limits",
            "G.L. c. 40P, § 4",
            C40P_SPAN,
            "State law bars local rent control; the corpus holds no acceptance of c. 40P or local rent control "
            "ordinance for this city, so no rent increase limit applies here (r-0079 is kept out of lookups).",
            d048,
        )


if __name__ == "__main__":
    from .merge import load_rules_file, save_rules_file

    rules_data = load_rules_file()
    add_static_findings(rules_data)
    save_rules_file(rules_data)
    print(f"{len(rules_data['no_rule_findings'])} no_rule_findings in out/rules.json")
