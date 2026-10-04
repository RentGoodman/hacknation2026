from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .corpus import DEFAULT_CORPUS_DIR, Document, load_corpus, normalize_jurisdiction
from .extract import _jurisdiction_and_level
from .schema import ExtractedRule, RuleRecord

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
EXTRA_DIR = REPO_ROOT / "corpus_extra"
RULES_PATH = REPO_ROOT / "out" / "rules.json"
CATEGORIES = [
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
]


def load_all_docs() -> list[Document]:
    return load_corpus(DEFAULT_CORPUS_DIR) + load_corpus(EXTRA_DIR)


def doc_jurisdiction(doc: Document) -> str:
    return normalize_jurisdiction(doc.jurisdictions)


def load_rules_file(path: Path = RULES_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_rules_file(data: dict[str, Any], path: Path = RULES_PATH) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(str.maketrans("‘’“”–—", "''\"\"--"))).strip().lower()


def next_id(rules: list[dict[str, Any]]) -> int:
    return max((int(r["team_rule_id"][2:]) for r in rules), default=0) + 1


def merge_rules(
    data: dict[str, Any],
    doc: Document,
    extracted: list[ExtractedRule],
    method: str,
    known_jurisdictions: set[str],
) -> list[dict[str, Any]]:
    rules = data["rules"]
    seen = {(r["category"], _norm(r["quoted_span"])) for r in rules}
    added: list[dict[str, Any]] = []
    for rule in extracted:
        key = (rule.category, _norm(rule.quoted_span))
        if key in seen:
            log.info("%s: %s already in rules.json, skipped", doc.doc_id, rule.title)
            continue
        jurisdiction, level = _jurisdiction_and_level(rule, doc.doc_id, known_jurisdictions)
        coverage = rule.coverage_conditions
        try:
            record = RuleRecord(
                team_rule_id=f"r-{next_id(rules):04d}",
                source_doc_id=doc.doc_id,
                source_url=doc.url,
                overrides=[],
                **rule.model_dump(exclude={"jurisdiction", "level", "coverage_conditions"}),
                jurisdiction=jurisdiction,
                level=level,
                coverage_conditions=None if coverage.is_empty() else coverage.model_dump(),
            )
        except ValidationError as e:
            log.warning("%s: rule %r failed validation: %s", doc.doc_id, rule.title, e)
            continue
        out = record.model_dump(mode="json")
        out["extraction_method"] = method
        rules.append(out)
        seen.add(key)
        added.append(out)
    return added
