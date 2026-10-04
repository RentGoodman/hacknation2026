import hashlib
import json
import time
from pathlib import Path

from .classify_conditions import _ask

CACHE = Path(__file__).resolve().parent / "cache" / "overrides.json"
DECISIONS = {"REAL_SUPERSESSION", "COEXISTS", "UNCERTAIN"}
FIELDS = ("team_rule_id", "jurisdiction", "level", "category", "title", "requirement", "key_value", "citation",
          "interaction", "quoted_span")

PROMPT = """Two US landlord-tenant rules are linked as possibly overriding each other.

Rule A:
{a}

Rule B:
{b}

Decide, for a building where both rules could apply:
- REAL_SUPERSESSION: one rule actually displaces the other (the other does not apply, e.g. local rent control exempts units from the state cap).
- COEXISTS: both apply at the same time (e.g. one adds an obligation, a minimum, or credits against the other).
- UNCERTAIN: the texts do not settle it.
If REAL_SUPERSESSION, give the team_rule_id of the rule that governs as "winner".
Answer with JSON only: {{"decision": "...", "winner": "r-xxxx or null", "reason": "one line"}}"""

_current = {}


def edges(rules):
    by = {r["team_rule_id"]: r for r in rules}
    out = set()
    for r in rules:
        for o in r.get("overrides") or []:
            if o in by and o != r["team_rule_id"]:
                out.add(tuple(sorted((r["team_rule_id"], o))))
    return sorted(out)


def _key(a, b):
    h = hashlib.sha256(json.dumps([[a.get(f) for f in FIELDS], [b.get(f) for f in FIELDS]], sort_keys=True)
                       .encode()).hexdigest()[:16]
    return f"{a['team_rule_id']}|{b['team_rule_id']}:{h}"


def _show(r):
    return json.dumps({f: r.get(f) for f in FIELDS}, ensure_ascii=False, indent=1)


def audit(rules, use_api=True):
    global _current
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    by = {r["team_rule_id"]: r for r in rules}
    result, err, dirty = {}, None, False
    skipped = []
    for x, y in edges(rules):
        k = _key(by[x], by[y])
        entry = cache.get(k)
        if entry is None and use_api and err is None:
            for attempt in range(2):
                try:
                    raw, label = _ask(PROMPT.format(a=_show(by[x]), b=_show(by[y])))
                    d = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
                    dec = d.get("decision") if d.get("decision") in DECISIONS else "UNCERTAIN"
                    win = d.get("winner") if d.get("winner") in (x, y) else None
                    if dec == "REAL_SUPERSESSION" and win is None:
                        dec = "UNCERTAIN"
                    entry = {"pair": [x, y], "decision": dec, "winner": win,
                             "reason": (d.get("reason") or "").strip(), "model": label}
                    cache[k], dirty = entry, True
                    break
                except Exception as e:
                    if attempt == 0:
                        time.sleep(5)
                        continue
                    msg = f"{type(e).__name__}: {str(e)[:160]}"
                    if any(w in msg.lower() for w in ("rate", "quota", "429", "credit", "overloaded", "529")):
                        err = msg
                    else:
                        skipped.append(f"{x}|{y}: {msg}")
        if entry is not None:
            result[frozenset((x, y))] = entry
    if dirty:
        CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    _current = result
    if skipped and not err:
        err = f"{len(skipped)} edge(s) skipped after retry: " + "; ".join(skipped[:5])
    return result, err


def current_audit():
    return _current


def write_report(rules, result, path):
    by = {r["team_rule_id"]: r for r in rules}
    es = edges(rules)
    counts = {}
    lines = ["# Overrides audit", "",
             "One Claude call per overrides edge (engine/audit_overrides.py, cache engine/cache/overrides.json). "
             "REAL_SUPERSESSION: the winner supersedes the other. COEXISTS: the edge is ignored. UNCERTAIN: no "
             "supersession, conflict_flag true with the reason. Edges not audited keep the interaction-text direction.",
             "", "| rule A | rule B | decision | winner | reason |", "|---|---|---|---|---|"]
    for x, y in es:
        e = result.get(frozenset((x, y)))
        dec = e["decision"] if e else "NOT_AUDITED"
        counts[dec] = counts.get(dec, 0) + 1
        reason = (e["reason"] if e else "no cached decision").replace("|", "/")
        lines.append(f"| {x} ({by[x]['jurisdiction']}, {by[x]['category']}) | {y} ({by[y]['jurisdiction']}) | "
                     f"{dec} | {(e or {}).get('winner') or '-'} | {reason} |")
    lines[2:2] = ["Totals: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f" (edges: {len(es)})", ""]
    Path(path).write_text("\n".join(lines) + "\n")
    return counts


def main():
    from .prepare import prepare_rules
    from .rules import load_rules
    rules, source, _ = load_rules()
    rules, _ = prepare_rules(rules)
    result, err = audit(rules)
    print(f"audited {len(result)}/{len(edges(rules))} edges from {source}" + (f"; stopped: {err}" if err else ""))


if __name__ == "__main__":
    main()
