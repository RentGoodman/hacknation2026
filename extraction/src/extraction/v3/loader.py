from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .client import ROOT, sha256_text

STARTER = ROOT / "starter pack" / "corpus"
EXTRA = ROOT / "corpus_extra"
MANIFESTS = [(STARTER / "corpus_manifest.csv", STARTER), (EXTRA / "corpus_manifest.csv", EXTRA)]

NAV_MAX_LEN = 120
NAV_MIN_DOCS = 3


@dataclass
class Doc:
    doc_id: str
    jurisdictions: str
    url: str
    source_type: str
    retrieved_at: str
    raw: str
    body_start: int = 0
    text: str = ""
    clean_to_raw: list[int] = field(default_factory=list, repr=False)
    dropped_lines: int = 0

    @property
    def sha256(self) -> str:
        return sha256_text(self.raw)

    @property
    def host(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")

    @property
    def official(self) -> bool:
        return self.source_type.strip().lower().startswith("official")

    def raw_span(self, start: int, end: int) -> str:
        return self.raw[self.clean_to_raw[start]: self.clean_to_raw[end - 1] + 1]


@dataclass
class LinkOnly:
    doc_id: str
    jurisdictions: str
    url: str
    source_type: str


def _body_start(raw: str) -> int:
    pos = 0
    for line in raw.splitlines(keepends=True)[:6]:
        if line.startswith(("SOURCE:", "RETRIEVED:", "NOTE:")) or (pos and not line.strip()):
            pos += len(line)
            continue
        break
    return pos


def _norm_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()


def _nav_lines(docs: list[Doc]) -> dict[str, set[str]]:
    by_host: dict[str, list[Doc]] = defaultdict(list)
    for d in docs:
        by_host[d.host].append(d)
    out: dict[str, set[str]] = {}
    for host, group in by_host.items():
        if len(group) < NAV_MIN_DOCS:
            continue
        counts: Counter[str] = Counter()
        for d in group:
            counts.update({_norm_line(l) for l in d.raw[d.body_start:].splitlines()
                           if 0 < len(l.strip()) <= NAV_MAX_LEN})
        out[host] = {l for l, n in counts.items() if n >= NAV_MIN_DOCS and not _looks_like_law(l)}
    return out


_LAW = re.compile(r"(§|section|sec\.|shall|tenant|landlord|rent|deposit|evict|\d+\.\d+)", re.I)


def _looks_like_law(line: str) -> bool:
    return bool(_LAW.search(line))


def _clean(doc: Doc, nav: set[str]) -> None:
    pieces: list[str] = []
    mapping: list[int] = []
    pos = doc.body_start
    dropped = 0
    for line in doc.raw[doc.body_start:].splitlines(keepends=True):
        if nav and _norm_line(line) in nav:
            dropped += 1
        else:
            pieces.append(line)
            mapping.extend(range(pos, pos + len(line)))
        pos += len(line)
    doc.text = "".join(pieces)
    doc.clean_to_raw = mapping
    doc.dropped_lines = dropped


def load(doc_ids: list[str] | None = None, extra_paths: list[tuple[Path, Path]] | None = None
         ) -> tuple[list[Doc], list[LinkOnly]]:
    docs: list[Doc] = []
    links: list[LinkOnly] = []
    for manifest, base in MANIFESTS + (extra_paths or []):
        if not manifest.exists():
            continue
        with manifest.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") != "ok" or not row.get("text_file"):
                    links.append(LinkOnly(row["doc_id"], row["jurisdictions"], row["url"], row["source_type"]))
                    continue
                raw = (base / row["text_file"]).read_text(encoding="utf-8")
                docs.append(Doc(row["doc_id"], row["jurisdictions"], row["url"], row["source_type"],
                                row.get("retrieved_at", ""), raw, _body_start(raw)))
    nav = _nav_lines(docs)
    for d in docs:
        _clean(d, nav.get(d.host, set()))
    if doc_ids:
        wanted = set(doc_ids)
        docs = [d for d in docs if d.doc_id in wanted]
    docs.sort(key=lambda d: d.doc_id)
    return docs, links
