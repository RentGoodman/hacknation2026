from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from langchain_core.language_models import BaseChatModel

from .corpus import DEFAULT_CORPUS_DIR, Document, load_corpus, load_jurisdictions
from .extract import DocExtraction, Extractor, assemble
from .link import Linker, apply_links, group_rules, link_all, stale_groups
from .llm import DEFAULT_MODEL, build_model, structured_output_method

log = logging.getLogger("extraction")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="extraction", description="Extract rule records from the corpus with an LLM.")
    p.add_argument(
        "--model",
        default=os.environ.get("EXTRACTION_MODEL", DEFAULT_MODEL),
        help="'provider:model' string; anthropic:/claude_cli: models use the Claude subscription via `claude -p`, "
        "others any LangChain provider (default: $EXTRACTION_MODEL or %(default)s)",
    )
    p.add_argument("--docs", nargs="+", metavar="DOC_ID", help="Only these doc_ids (default: all with text)")
    p.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    p.add_argument("--out-dir", type=Path, default=Path("out"))
    p.add_argument("--query-date", default="2026-10-01", help="Date that rule status is judged against")
    p.add_argument("--concurrency", type=int, default=10, help="Max parallel LLM calls")
    p.add_argument("--max-chars", type=int, default=60_000, help="Split documents longer than this")
    p.add_argument("--temperature", type=float, help="Sampling temperature (default: provider default)")
    p.add_argument("--max-tokens", type=int, help="Max output tokens (default: provider default)")
    p.add_argument(
        "--structured-method",
        choices=["auto", "json_schema", "function_calling", "json_mode"],
        default="auto",
        help="How to get structured output; 'auto' uses native JSON schema where supported",
    )
    p.add_argument("--force", action="store_true", help="Re-extract documents that are already cached")
    p.add_argument("--no-link", action="store_true", help="Skip linking rules across documents (overrides)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


async def _extract_all(extractor: Extractor, docs: list[Document], cache_dir: Path) -> int:
    async def run(doc: Document) -> bool:
        try:
            extraction = await extractor.extract(doc)
        except Exception:
            log.exception("%s: extraction failed", doc.doc_id)
            return False
        (cache_dir / f"{doc.doc_id}.json").write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
        log.info("%s: %d rule(s) from %d chunk(s)", doc.doc_id, len(extraction.rules), extraction.chunks)
        return True

    results = await asyncio.gather(*(run(doc) for doc in docs))
    return results.count(False)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    cache_dir = args.out_dir / "docs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    structured_method = structured_output_method(args.model, args.structured_method)

    model: BaseChatModel | None = None

    def get_model() -> BaseChatModel:
        nonlocal model
        if model is None:
            model = build_model(args.model, args.temperature, args.max_tokens)
        return model

    docs = load_corpus(args.corpus_dir, args.docs)
    todo = [d for d in docs if args.force or not (cache_dir / f"{d.doc_id}.json").exists()]
    log.info("%d document(s) selected, %d to extract with %s", len(docs), len(todo), args.model)

    failures = 0
    if todo:
        extractor = Extractor(
            get_model(),
            model_name=args.model,
            query_date=args.query_date,
            max_chars=args.max_chars,
            concurrency=args.concurrency,
            structured_method=structured_method,
        )
        failures = asyncio.run(_extract_all(extractor, todo, cache_dir))

    extractions = [
        DocExtraction.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(cache_dir.glob("*.json"))
    ]
    records, rejected = assemble(extractions, load_jurisdictions(args.corpus_dir))

    if not args.no_link:
        links_path = args.out_dir / "links.json"
        cache = json.loads(links_path.read_text(encoding="utf-8")) if links_path.exists() else {}
        groups = group_rules(records)
        stale = stale_groups(groups, cache, args.query_date)
        log.info("%d rule group(s) to link, %d changed since last run", len(groups), len(stale))
        if stale:
            linker = Linker(
                get_model(),
                model_name=args.model,
                query_date=args.query_date,
                concurrency=args.concurrency,
                structured_method=structured_method,
            )
            cache, link_failures = asyncio.run(link_all(linker, stale, cache))
            failures += link_failures
        cache = {key: entry for key, entry in cache.items() if key in groups}
        links_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        apply_links(records, cache)

    rules_path = args.out_dir / "rules.json"
    rules_path.write_text(
        json.dumps({"rules": [r.model_dump(mode="json") for r in records]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (args.out_dir / "rejected.json").write_text(json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(
        "Wrote %d rule(s) from %d document(s) to %s (%d rejected, %d linked, %d flagged)",
        len(records),
        len(extractions),
        rules_path,
        len(rejected),
        sum(bool(r.overrides) for r in records),
        sum(r.conflict_flag for r in records),
    )
    if failures:
        log.error("%d document(s) or rule group(s) failed; rerun to retry them", failures)
        sys.exit(1)
