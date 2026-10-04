from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, ValidationError

from .corpus import Document, level_for, normalize_jurisdiction
from .llm import PROMPT, structured_chain
from .llmlog import DEFAULT_CONCURRENCY, AuditedChain
from .schema import ExtractedRule, ExtractionResult, RuleRecord
from .spans import SpanLocator

log = logging.getLogger(__name__)


class DocExtraction(BaseModel):

    doc_id: str
    source_url: str
    model: str
    query_date: str
    chunks: int
    rules: list[ExtractedRule]
    rejected: list[dict[str, Any]]


class Extractor:
    def __init__(
        self,
        model: BaseChatModel | None,
        model_name: str,
        query_date: str,
        max_chars: int = 60_000,
        concurrency: int = DEFAULT_CONCURRENCY,
        retries: int = 3,
        structured_method: str | None = None,
        replay=None,
    ):
        self.model_name = model_name
        self.query_date = query_date
        self.max_chars = max_chars
        chain: Runnable | None = (
            structured_chain(PROMPT, model, ExtractionResult, structured_method, retries) if model is not None else None
        )
        self.chain = AuditedChain(chain, PROMPT, ExtractionResult, model_name, "extract", replay=replay)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chars,
            chunk_overlap=min(2_000, max_chars // 10),
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self._semaphore = asyncio.Semaphore(concurrency)

    def _chunks(self, text: str) -> list[str]:
        return [text] if len(text) <= self.max_chars else self.splitter.split_text(text)

    async def _run_chunk(self, doc: Document, chunk: str, part: int, total: int) -> ExtractionResult:
        chunk_note = (
            f"This is part {part} of {total} of the document. Extract only rules supported by this part.\n"
            if total > 1
            else ""
        )
        async with self._semaphore:
            return await self.chain.ainvoke(
                {
                    "query_date": self.query_date,
                    "doc_id": doc.doc_id,
                    "jurisdictions": doc.jurisdictions,
                    "source_type": doc.source_type,
                    "url": doc.url,
                    "chunk_note": chunk_note,
                    "text": chunk,
                },
                context={"doc_id": doc.doc_id, "part": part},
            )

    async def extract(self, doc: Document) -> DocExtraction:
        chunks = self._chunks(doc.text)
        results = await asyncio.gather(
            *(self._run_chunk(doc, chunk, i, len(chunks)) for i, chunk in enumerate(chunks, start=1))
        )

        locator = SpanLocator(doc.text)
        kept: list[ExtractedRule] = []
        rejected: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for rule in (r for result in results for r in result.rules):
            exact = locator.locate(rule.quoted_span)
            if exact is None:
                rejected.append({"reason": "quoted_span not found in source text", "rule": rule.model_dump()})
                continue
            if len(exact) < 20:
                rejected.append({"reason": "quoted_span shorter than 20 characters", "rule": rule.model_dump()})
                continue
            key = (rule.category, exact)
            if key in seen:
                continue
            seen.add(key)
            kept.append(rule.model_copy(update={"quoted_span": exact}))

        if rejected:
            log.warning("%s: rejected %d rule(s) with unverifiable quotes", doc.doc_id, len(rejected))
        return DocExtraction(
            doc_id=doc.doc_id,
            source_url=doc.url,
            model=self.model_name,
            query_date=self.query_date,
            chunks=len(chunks),
            rules=kept,
            rejected=rejected,
        )


def _jurisdiction_and_level(rule: ExtractedRule, doc_id: str, known: set[str]) -> tuple[str, str]:
    jurisdiction = normalize_jurisdiction(rule.jurisdiction)
    level = level_for(jurisdiction)
    if known and jurisdiction not in known:
        log.warning("%s: jurisdiction %r is not in the corpus manifest", doc_id, jurisdiction)
    if level != rule.level:
        log.warning(
            "%s: %r labelled %s by the model; using %s (%s)", doc_id, rule.title, rule.level, level, jurisdiction
        )
    return jurisdiction, level


def assemble(
    extractions: list[DocExtraction], known_jurisdictions: set[str] | None = None
) -> tuple[list[RuleRecord], list[dict[str, Any]]]:
    records: list[RuleRecord] = []
    rejected: list[dict[str, Any]] = []
    for extraction in sorted(extractions, key=lambda e: e.doc_id):
        rejected.extend({"doc_id": extraction.doc_id, **r} for r in extraction.rejected)
        for rule in extraction.rules:
            jurisdiction, level = _jurisdiction_and_level(rule, extraction.doc_id, known_jurisdictions or set())
            coverage = rule.coverage_conditions
            try:
                record = RuleRecord(
                    team_rule_id=f"r-{len(records) + 1:04d}",
                    source_doc_id=extraction.doc_id,
                    source_url=extraction.source_url,
                    overrides=[],
                    **rule.model_dump(exclude={"jurisdiction", "level", "coverage_conditions"}),
                    jurisdiction=jurisdiction,
                    level=level,
                    coverage_conditions=None if coverage.is_empty() else coverage.model_dump(),
                )
            except ValidationError as e:
                rejected.append({"doc_id": extraction.doc_id, "reason": str(e), "rule": rule.model_dump()})
                continue
            records.append(record)
    return records, rejected
