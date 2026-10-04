import hashlib
import json
import re
import time
from pathlib import Path

from .classify_conditions import STOP_MARKERS, _ask, _forget

CACHE = Path(__file__).resolve().parent / "cache" / "validity.json"
VERSION = "v1"
DATEISH = re.compile(r"\b(19|20)\d{2}\b|\b(january|february|march|april|may|june|july|august|september|october|"
                     r"november|december)\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", re.I)
PROMPT = """A landlord-tenant record may contain either (a) a rate, fee, payment amount or other FIGURE published
for a limited period, while the underlying law continues, or (b) an explicit repeal/sunset of THE LAW ITSELF.
Classify the end date. Effective/adoption dates and dates about tenancies, deposits or notices are neither kind.

Title: {title}
Requirement: {requirement}
Key value: {key_value}
Quoted source: {quoted_span}

Answer with JSON only: {{"kind": "figure_period" or "law_sunset" or null, "end_date": "YYYY-MM-DD" or null,
"clause": "the exact words stating the end, copied verbatim from the texts above" or null}}"""


def _text(r):
    return " ".join(str(r.get(k) or "") for k in ("title", "requirement", "key_value", "quoted_span"))


def _key(r):
    h = hashlib.sha256(_text(r).encode()).hexdigest()[:16]
    return f"{r['team_rule_id']}:{VERSION}:{h}"


def _norm(t):
    return " ".join(re.sub(r"[–—]", "-", t or "").lower().split())


def attach(rules, use_api=False):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    log, err, dirty = [], None, False
    for r in sorted(rules, key=lambda x: x["team_rule_id"]):
        if not DATEISH.search(_text(r)):
            continue
        k = _key(r)
        entry = cache.get(k)
        if entry is None and use_api and err is None:
            prompt = PROMPT.format(**{f: r.get(f) or "" for f in ("title", "requirement", "key_value", "quoted_span")})
            for attempt in range(2):
                try:
                    raw, label = _ask(prompt)
                    try:
                        d = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
                    except ValueError:
                        _forget(prompt)
                        raise
                    kind, end, clause = d.get("kind"), d.get("end_date"), d.get("clause")
                    ok = bool(kind in ("figure_period", "law_sunset") and end and clause
                              and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end)
                              and _norm(clause) in _norm(_text(r)))
                    entry = {"kind": kind if ok else None, "end_date": end if ok else None,
                             "clause": clause if ok else None,
                             "rejected": None if ok or not end else f"clause not verbatim or bad date: {clause!r}",
                             "model": label}
                    cache[k], dirty = entry, True
                    break
                except Exception as e:
                    msg = f"{type(e).__name__}: {str(e)[:160]}"
                    stop = any(w in msg.lower() for w in STOP_MARKERS)
                    if attempt == 0 and not stop:
                        time.sleep(5)
                        continue
                    if stop:
                        err = msg
                        break
        if entry:
            kind = entry.get("kind") or ("figure_period" if entry.get("valid_until") else None)
            end = entry.get("end_date") or entry.get("valid_until")
            if kind == "figure_period" and end:
                r["figure_period_end"] = end
                r["_figure_period_clause"] = entry["clause"]
                log.append({"team_rule_id": r["team_rule_id"], "kind": kind,
                            "figure_period_end": end, "clause": entry["clause"]})
            elif kind == "law_sunset" and end:
                r["valid_until"] = end
                r["_valid_until_clause"] = entry["clause"]
                log.append({"team_rule_id": r["team_rule_id"], "kind": kind,
                            "valid_until": end, "clause": entry["clause"]})
    if dirty:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    return log, err


def main():
    from .prepare import prepare_rules
    from .rules import load_rules
    rules, source, _ = load_rules()
    rules, _ = prepare_rules(rules)
    log, err = attach(rules, use_api=True)
    print(f"temporal periods found for {len(log)} rules from {source}" + (f"; stopped: {err}" if err else ""))


if __name__ == "__main__":
    main()
