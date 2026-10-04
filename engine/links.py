import json

from .rules import ROOT, _git_show

CANDIDATES_LOCAL = [ROOT / "out" / "links.json"]
CANDIDATES_GIT = [("origin/main", "out/links.json")]
EMPTY = {"supersedes": set(), "conflicts": set(), "uncertain": set(), "source": None, "count": 0}
_current = dict(EMPTY)


def _parse(data, source):
    items = data.get("links", data) if isinstance(data, dict) else data
    out = {"supersedes": set(), "conflicts": set(), "uncertain": set(), "source": source, "count": len(items)}
    for l in items:
        a = l.get("from") or l.get("source") or l.get("rule_id")
        b = l.get("to") or l.get("target") or l.get("other_rule_id")
        t = (l.get("type") or l.get("relation") or "").lower()
        if not a or not b:
            continue
        if l.get("uncertain") or t == "uncertain":
            out["uncertain"].add(frozenset((a, b)))
        elif t in ("supersedes", "overrides", "preempts"):
            out["supersedes"].add((a, b))
        elif t in ("conflicts", "conflict"):
            out["conflicts"].add(frozenset((a, b)))
    return out


def load_links():
    global _current
    for p in CANDIDATES_LOCAL:
        if p.exists():
            _current = _parse(json.loads(p.read_text()), str(p.relative_to(ROOT)))
            return _current
    for ref, path in CANDIDATES_GIT:
        text = _git_show(ref, path)
        if text:
            _current = _parse(json.loads(text), f"{ref}:{path}")
            return _current
    _current = dict(EMPTY)
    return _current


def current_links():
    return _current


def links_log():
    c = _current
    if not c["source"]:
        return {"links_source": None, "links_note": "links.json not found on local out/, origin/main; precedence uses rule overrides only."}
    return {"links_source": c["source"], "links_count": c["count"], "supersedes": len(c["supersedes"]),
            "conflicts": len(c["conflicts"]), "uncertain": len(c["uncertain"])}
