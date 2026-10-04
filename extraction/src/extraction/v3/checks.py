from __future__ import annotations

import math
import re
from collections import Counter

_TOK = re.compile(r"[a-z0-9]+")
DUP_MIN, SPLIT_MAX = 0.8, 0.3


def _vec(text: str, idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(_TOK.findall(text.lower()))
    v = {t: c * idf.get(t, 0.0) for t, c in tf.items()}
    n = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {t: x / n for t, x in v.items()}


def _cos(a: dict, b: dict) -> float:
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def _text(r: dict) -> str:
    return " ".join(str(r.get(k) or "") for k in ("title", "requirement", "quoted_span"))


def merge_findings(rules: list[dict], candidates: dict[str, dict]) -> list[dict]:
    corpus = [_text(r) for r in rules] + [_text(c) for c in candidates.values()]
    df = Counter(t for doc in corpus for t in set(_TOK.findall(doc.lower())))
    idf = {t: math.log((1 + len(corpus)) / (1 + f)) + 1 for t, f in df.items()}
    out = []
    for i, a in enumerate(rules):
        for b in rules[i + 1:]:
            if (a["jurisdiction"], a["category"]) != (b["jurisdiction"], b["category"]):
                continue
            if a.get("status") in ("pending", "failed") or b.get("status") in ("pending", "failed"):
                continue
            s = _cos(_vec(_text(a), idf), _vec(_text(b), idf))
            if s >= DUP_MIN:
                out.append({"kind": "unmerged_similar", "jurisdiction": a["jurisdiction"], "category": a["category"],
                            "titles": [a["title"], b["title"]], "similarity": round(s, 3)})
    for r in rules:
        members = [candidates[c] for c in r.get("from_candidates", []) if c in candidates]
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                s = _cos(_vec(_text(a), idf), _vec(_text(b), idf))
                if s < SPLIT_MAX:
                    out.append({"kind": "merged_dissimilar", "jurisdiction": r["jurisdiction"],
                                "category": r["category"], "rule": r["title"],
                                "candidates": [a["candidate_id"], b["candidate_id"]], "similarity": round(s, 3)})
    return out


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_ok(summary: str, record: dict) -> bool:
    hay = " ".join(str(v) for v in record.values() if v is not None)
    hay_nums = {n.replace(",", "") for n in _NUM.findall(hay)}
    return all(n.replace(",", "") in hay_nums for n in _NUM.findall(summary))
