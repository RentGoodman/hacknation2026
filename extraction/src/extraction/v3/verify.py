from __future__ import annotations

from difflib import SequenceMatcher

from ..spans import SpanLocator

SNAP_MIN = 0.55


def exact_or_normalized(raw: str, span: str | None) -> tuple[str | None, str]:
    if not span:
        return None, "empty"
    if span in raw:
        return span, "exact"
    found = SpanLocator(raw).locate(span)
    return (found, "normalized") if found else (None, "missing")


def snap(raw: str, span: str) -> tuple[str | None, float]:
    n = len(span)
    if not n or not raw:
        return None, 0.0
    best, best_ratio = None, 0.0
    step = max(1, n // 8)
    sm = SequenceMatcher(autojunk=False)
    sm.set_seq2(span)
    for size in {n, int(n * 0.8), int(n * 1.2)}:
        for start in range(0, max(1, len(raw) - size + 1), step):
            window = raw[start:start + size]
            sm.set_seq1(window)
            if sm.real_quick_ratio() < best_ratio or sm.quick_ratio() < best_ratio:
                continue
            r = sm.ratio()
            if r > best_ratio:
                best, best_ratio = (start, size), r
    if best is None or best_ratio < SNAP_MIN:
        return None, best_ratio
    start, size = best
    while start > 0 and not raw[start - 1].isspace():
        start -= 1
    end = start + size
    while end < len(raw) and not raw[end].isspace():
        end += 1
    found = raw[start:end].strip()
    if _word_overlap(span, found) < WORD_OVERLAP_MIN:
        return None, best_ratio
    return found, best_ratio


WORD_OVERLAP_MIN = 0.5


def _words(t: str) -> set[str]:
    import re

    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 3}


def _word_overlap(span: str, found: str) -> float:
    w = _words(span)
    return len(w & _words(found)) / len(w) if w else 0.0
