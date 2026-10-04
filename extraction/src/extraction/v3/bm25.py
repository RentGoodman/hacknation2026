from __future__ import annotations

import math
import re
from collections import Counter

from .loader import Doc

PASSAGE = 1200
QUERIES = {
    "rent_increase_limits": "rent increase cap limit percent annual allowable rent control stabilization CPI",
    "just_cause_eviction": "just cause eviction terminate tenancy notice quit relocation assistance no-fault",
    "security_deposits": "security deposit return interest month rent deduction itemized",
    "application_screening_fees": "application fee screening fee charge refund receipt broker fee",
    "screening_restrictions": "criminal history source of income credit screening applicant consider",
    "algorithmic_rent_setting": "algorithm algorithmic software pricing rent-setting coordinated competitor data",
}
_TOK = re.compile(r"[a-z0-9]+")


def _tok(t: str) -> list[str]:
    return _TOK.findall(t.lower())


class Index:
    def __init__(self, docs: list[Doc], k1: float = 1.5, b: float = 0.75):
        self.passages: list[tuple[str, int, str]] = []
        for d in docs:
            for start in range(0, len(d.text), PASSAGE):
                self.passages.append((d.doc_id, start, d.text[start:start + PASSAGE]))
        self.tf = [Counter(_tok(p[2])) for p in self.passages]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / max(1, len(self.len))
        df: Counter[str] = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(self.tf)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, k: int = 8) -> list[tuple[str, int, str]]:
        return [self.passages[i] for _, i in self.scored(query)[:k]]

    def scored(self, query: str) -> list[tuple[float, int]]:
        q = _tok(query)
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            if s:
                scores.append((s, i))
        scores.sort(key=lambda x: (-x[0], x[1]))
        return scores


def probe_passages(index: Index, jurisdiction: str, category: str, k: int = 8) -> str:
    city = jurisdiction.split(",")[0]
    hits = index.search(f"{city} {jurisdiction} {QUERIES[category]}", k)
    return "\n".join(f'<passage doc="{d}" offset="{o}" category="{category}">\n{t}\n</passage>' for d, o, t in hits)
