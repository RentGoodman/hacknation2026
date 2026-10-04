from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .corpus import Document, _strip_header, normalize_jurisdiction
from .extract import Extractor
from .llm import DEFAULT_MODEL, build_model, structured_output_method
from .llmlog import DEFAULT_CONCURRENCY
from .merge import EXTRA_DIR, REPO_ROOT, load_all_docs, load_rules_file, merge_rules, save_rules_file
from .schema import ExtractionResult

log = logging.getLogger("extraction.ingest_new")
CHANGES_PATH = REPO_ROOT / "out" / "changes.json"


def _fetch(url: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "src"
        subprocess.run(["curl", "-sSLf", "-m", "120", "-o", str(path), url], check=True)
        return _to_text(path)


def _to_text(path: Path) -> str:
    if path.read_bytes()[:5] == b"%PDF-":
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
    text = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"<html|<body", text[:2000], re.I):
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", "\n", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text


def _next_doc_id() -> str:
    used = [int(m.group(1)) for p in EXTRA_DIR.glob("DX*.txt") if (m := re.fullmatch(r"DX(\d+)\.txt", p.name))]
    return f"DX{max(used, default=0) + 1:02d}"


def _next_test_id() -> str:
    changes = json.loads(CHANGES_PATH.read_text(encoding="utf-8")) if CHANGES_PATH.exists() else {}
    used = [int(k[1:]) for k in changes if re.fullmatch(r"T\d+", k)]
    return f"T{max(used, default=0) + 1}"


def save_source(doc_id: str, jurisdiction: str, source: str, text: str) -> Document:
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    body = text.strip("\n")
    (EXTRA_DIR / f"{doc_id}.txt").write_text(f"SOURCE: {source}\nRETRIEVED: {retrieved}\n\n{body}\n", encoding="utf-8")
    source_type = "official" if source.startswith("http") else "local file"
    with (EXTRA_DIR / "corpus_manifest.csv").open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([doc_id, jurisdiction, source, source_type, "yes", retrieved, "", f"{doc_id}.txt", "ok"])
    import hashlib

    sha = hashlib.sha256((EXTRA_DIR / f"{doc_id}.txt").read_bytes()).hexdigest()
    with (EXTRA_DIR / "manifest_extra.csv").open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([doc_id, jurisdiction, source, source_type, "yes", retrieved, sha, "added by ingest_new"])
    return Document(doc_id, jurisdiction, source, source_type, retrieved, _strip_header(body))


_COMPARE = r"""
import json, sys
from datetime import date, timedelta
from engine.run import evaluation_context
from engine.verdict import DEFAULT_AS_OF, lookups
ids, eff = set(json.loads(sys.argv[1])), sys.argv[2] or None
ctx = evaluation_context(fetch=False)
b, rules = ctx["buildings"], ctx["rules"]
def pick(L):
    return {a: {e["team_rule_id"]: e["result"] for e in es if e["team_rule_id"] in ids} for a, es in L.items()}
if eff:
    before_date, after_date = (date.fromisoformat(eff) - timedelta(days=1)).isoformat(), eff
    before, after = pick(lookups(b, rules, before_date)), pick(lookups(b, rules, after_date))
    mode = {"before": before_date, "after": after_date, "basis": "effective_date"}
else:
    before = pick(lookups(b, [r for r in rules if r["team_rule_id"] not in ids], DEFAULT_AS_OF))
    after = pick(lookups(b, rules, DEFAULT_AS_OF))
    mode = {"before": DEFAULT_AS_OF + " (without new rules)", "after": DEFAULT_AS_OF + " (with new rules)",
            "basis": "no effective date extracted"}
rows = {}
for a in sorted(b):
    x = {i: before[a].get(i, "omitted") for i in sorted(ids)}
    y = {i: after[a].get(i, "omitted") for i in sorted(ids)}
    if x != y:
        rows[a] = {"before": x, "after": y}
print(json.dumps({"mode": mode, "rows": rows}))
"""


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    p = argparse.ArgumentParser(prog="extraction.ingest_new", description="Ingest one new law end to end.")
    p.add_argument("--jurisdiction", required=True, help='"CA" or "City, ST"')
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", type=Path)
    src.add_argument("--url")
    p.add_argument("--test-id", help="Change test id (default: next free T<n>)")
    p.add_argument("--doc-id", help="Corpus id (default: next free DX<nn>)")
    p.add_argument("--model", default=os.environ.get("EXTRACTION_MODEL", DEFAULT_MODEL))
    p.add_argument("--query-date", default="2026-10-01")
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    p.add_argument("--replay", type=Path, help="TEST ONLY: canned ExtractionResult JSON instead of the model")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    timing: dict[str, float] = {}
    t0 = time.perf_counter()

    jurisdiction = normalize_jurisdiction(args.jurisdiction)
    doc_id = args.doc_id or _next_doc_id()
    test_id = args.test_id or _next_test_id()
    text = _to_text(args.file) if args.file else _fetch(args.url)
    source = args.url or f"file:{args.file}"
    doc = save_source(doc_id, jurisdiction, source, text)
    timing["save_source"] = time.perf_counter() - t0

    t = time.perf_counter()
    replay = None
    model = None
    model_name = args.model
    if args.replay:
        canned = ExtractionResult.model_validate_json(args.replay.read_text(encoding="utf-8"))
        replay, model_name = (lambda _inputs: canned), f"replay:{args.replay.name}"
    else:
        model = build_model(args.model)
    extractor = Extractor(
        model,
        model_name=model_name,
        query_date=args.query_date,
        concurrency=args.concurrency,
        structured_method=structured_output_method(args.model),
        replay=replay,
    )
    extraction = asyncio.run(extractor.extract(doc))
    cache_dir = REPO_ROOT / "extraction" / "out" / "docs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{doc_id}.json").write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
    timing["extract"] = time.perf_counter() - t

    t = time.perf_counter()
    data = load_rules_file()
    known = {normalize_jurisdiction(d.jurisdictions) for d in load_all_docs()}
    added = merge_rules(data, doc, extraction.rules, "pipeline", known)
    save_rules_file(data)
    ids = [r["team_rule_id"] for r in added]
    log.info("%s: %d rule(s) extracted, %d new: %s", doc_id, len(extraction.rules), len(added), ", ".join(ids) or "-")
    timing["merge"] = time.perf_counter() - t

    t = time.perf_counter()
    subprocess.run(["python3", "-m", "engine.run"], cwd=REPO_ROOT, check=True)
    timing["engine_500"] = time.perf_counter() - t

    t = time.perf_counter()
    dates = sorted({r["effective_date"] for r in added if r.get("effective_date")})
    eff = {4: "{}-01-01", 7: "{}-01"}.get(len(dates[0]), "{}").format(dates[0]) if dates else ""
    if ids:
        out = subprocess.run(
            ["python3", "-c", _COMPARE, json.dumps(ids), eff], cwd=REPO_ROOT, check=True, capture_output=True, text=True
        )
        cmp = json.loads(out.stdout)
    else:
        cmp = {"mode": {"basis": "no new rule"}, "rows": {}}
    changes = json.loads(CHANGES_PATH.read_text(encoding="utf-8"))
    changes[test_id] = {
        "affected_address_ids": sorted(cmp["rows"]),
        "conflict_flag_address_ids": [],
        "rule_ids": ids,
        "source_doc_id": doc_id,
        "jurisdiction": jurisdiction,
        "effective_date": eff or None,
        "compare": cmp["mode"],
        "results": cmp["rows"],
        "notes": (
            f"ingest_new: {doc_id} ({jurisdiction}) added {len(ids)} rule(s) {', '.join(ids) or '-'}; "
            f"{len(cmp['rows'])} address(es) change between {cmp['mode'].get('before')} and {cmp['mode'].get('after')}."
        ),
    }
    CHANGES_PATH.write_text(json.dumps(changes, indent=2) + "\n", encoding="utf-8")
    timing["change_test"] = time.perf_counter() - t
    timing["total"] = time.perf_counter() - t0
    print(json.dumps({"doc_id": doc_id, "test_id": test_id, "new_rule_ids": ids,
                      "affected": len(cmp["rows"]), "timing_s": {k: round(v, 2) for k, v in timing.items()}}, indent=2))


if __name__ == "__main__":
    sys.exit(main())
