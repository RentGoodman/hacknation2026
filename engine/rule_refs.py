import json
import sys

from .rules import ROOT

sys.path.insert(0, str(ROOT / "extraction" / "src"))
from extraction.normalize import law_key

REFS_PATH = ROOT / "engine" / "rule_refs.json"


def semantic_key(r):
    return f"{r['jurisdiction']}|{r['category']}|{law_key(r.get('citation'))}"


def _load(rules):
    if rules is None:
        rules = json.loads((ROOT / "out" / "rules.json").read_text())["rules"]
    return rules


def find_all(jurisdiction, category, citation=None, rules=None, status=None, keyword=None):
    key = law_key(citation) if citation else None
    out = []
    for r in _load(rules):
        if r["jurisdiction"] != jurisdiction or r["category"] != category:
            continue
        if status and r.get("status") not in ({status} if isinstance(status, str) else set(status)):
            continue
        if key:
            keys = {law_key(r.get("citation"))} | {law_key(a) for a in r.get("citation_aliases") or []}
            if not any(k == key or k.startswith(key) or key.startswith(k) for k in keys if k):
                continue
        if keyword:
            hay = " ".join([r.get("title") or "", r.get("citation") or "", *(r.get("citation_aliases") or [])])
            if keyword.lower() not in hay.lower():
                continue
        out.append(r)
    return sorted(out, key=lambda r: r["team_rule_id"])


def find(jurisdiction, category, citation=None, rules=None, status=None, keyword=None):
    hits = find_all(jurisdiction, category, citation, rules, status, keyword)
    return hits[0]["team_rule_id"] if hits else None


def by_canonical(canonical_id, rules=None):
    return next((r["team_rule_id"] for r in _load(rules) if r.get("canonical_id") == canonical_id), None)


def build(rules=None):
    return {semantic_key(r): r["team_rule_id"] for r in sorted(_load(rules), key=lambda r: r["team_rule_id"])}


DECISIONS_PATH = ROOT / "engine" / "rule_decisions.json"


def refresh_decisions(rules=None):
    rules = _load(rules)
    current = {r["team_rule_id"]: semantic_key(r) for r in rules}
    first = {}
    for r in sorted(rules, key=lambda r: r["team_rule_id"]):
        first.setdefault(semantic_key(r), r["team_rule_id"])
    decisions = json.loads(DECISIONS_PATH.read_text())
    for d in decisions:
        if current.get(d.get("team_rule_id")) != d["rule_key"]:
            d["team_rule_id"] = first.get(d["rule_key"])
    DECISIONS_PATH.write_text(json.dumps(decisions, indent=2, ensure_ascii=False) + "\n")
    return decisions


def main():
    REFS_PATH.write_text(json.dumps(build(), indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    refresh_decisions()
    print(f"wrote {REFS_PATH.relative_to(ROOT)}, refreshed {DECISIONS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
