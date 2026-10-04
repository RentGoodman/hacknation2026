from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[3] / "starter pack" / "corpus"


@dataclass(frozen=True)
class Document:
    doc_id: str
    jurisdictions: str
    url: str
    source_type: str
    retrieved_at: str
    text: str


def _strip_header(raw: str) -> str:
    lines = raw.splitlines(keepends=True)
    body_start = 0
    for i, line in enumerate(lines[:5]):
        if line.startswith(("SOURCE:", "RETRIEVED:")):
            body_start = i + 1
    return "".join(lines[body_start:]).strip("\n")


def load_corpus(corpus_dir: Path = DEFAULT_CORPUS_DIR, doc_ids: list[str] | None = None) -> list[Document]:
    wanted = set(doc_ids) if doc_ids else None
    docs: list[Document] = []
    with (corpus_dir / "corpus_manifest.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] != "ok" or not row["text_file"]:
                continue
            if wanted is not None and row["doc_id"] not in wanted:
                continue
            raw = (corpus_dir / row["text_file"]).read_text(encoding="utf-8")
            docs.append(
                Document(
                    doc_id=row["doc_id"],
                    jurisdictions=row["jurisdictions"],
                    url=row["url"],
                    source_type=row["source_type"],
                    retrieved_at=row["retrieved_at"],
                    text=_strip_header(raw),
                )
            )
    if wanted is not None:
        missing = wanted - {d.doc_id for d in docs}
        if missing:
            raise ValueError(f"No supplied text for: {', '.join(sorted(missing))}")
    return sorted(docs, key=lambda d: d.doc_id)


def load_jurisdictions(corpus_dir: Path = DEFAULT_CORPUS_DIR) -> set[str]:
    with (corpus_dir / "corpus_manifest.csv").open(newline="", encoding="utf-8") as f:
        return {row["jurisdictions"].strip() for row in csv.DictReader(f) if row["jurisdictions"].strip()}


_STATE_NAMES = {"california": "CA", "new jersey": "NJ", "massachusetts": "MA"}
_STATE_CODE = re.compile(r"[A-Z]{2}")


def normalize_jurisdiction(raw: str) -> str:
    text = " ".join(raw.split())
    if len(text) == 2:
        return text.upper()
    if text.lower() in _STATE_NAMES:
        return _STATE_NAMES[text.lower()]
    city, _, state = text.rpartition(",")
    if city:
        state = _STATE_NAMES.get(state.strip().lower(), state.strip().upper())
        city = re.sub(r"^(city|town) of\s+", "", city.strip(), flags=re.IGNORECASE)
        return f"{city}, {state}"
    return text


def level_for(jurisdiction: str) -> str:
    return "state" if _STATE_CODE.fullmatch(jurisdiction) else "city"
