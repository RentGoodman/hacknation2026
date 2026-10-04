from __future__ import annotations

import argparse
import asyncio
import json
import logging
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .corpus import normalize_jurisdiction
from .v3 import pipeline as PL
from .v3.client import LLM, ROOT
from .v3.loader import Doc, _body_start, load

DROP = ROOT / "corpus_extra" / "hour16"
log = logging.getLogger("extraction.ingest_new")


def _fetch(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "hacknation-ingest"}), timeout=60) as r:
        body = r.read()
    if body[:4] == b"%PDF":
        import io

        from pypdf import PdfReader

        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(body)).pages)
    return body.decode("utf-8", errors="replace")


def make_doc(doc_id: str, jurisdiction: str, text: str, url: str, source_type: str = "official") -> Doc:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    raw = text if text.startswith("SOURCE:") else f"SOURCE: {url}\nRETRIEVED: {now}\n\n{text}"
    d = Doc(doc_id, jurisdiction, url, source_type, now, raw, _body_start(raw))
    d.text = raw[d.body_start:]
    d.clean_to_raw = list(range(d.body_start, len(raw)))
    return d


def _as_candidates(rules: list[dict]) -> list[dict]:
    out = []
    for r in rules:
        c = dict(r)
        c["candidate_id"] = f"existing:{r['team_rule_id']}"
        c["coverage"] = {**(r.get("coverage_conditions") or {}), **(r.get("coverage") or {})}
        out.append(c)
    return out


def _engine(rules: list[dict], as_of: str) -> dict:
    import sys

    sys.path.insert(0, str(ROOT))
    from engine.audit_overrides import audit
    from engine.classify_conditions import classify
    from engine.prepare import prepare_rules
    from engine.rules import load_buildings
    from engine.validity import attach
    from engine.verdict import lookups

    buildings = load_buildings()
    prepared, _ = prepare_rules(json.loads(json.dumps(rules)))
    audit(prepared, use_api=False)
    classify(prepared, use_api=False)
    attach(prepared, use_api=False)
    return lookups(buildings, prepared, as_of)


def _affected(L: dict, ids: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for addr, entries in L.items():
        for e in entries:
            if e["team_rule_id"] in ids:
                out.setdefault(e["result"], []).append(addr)
    return {k: sorted(v) for k, v in sorted(out.items())}


async def ingest(doc: Doc, jurisdiction: str, test_id: str | None, out_dir: Path, offline: bool | None) -> dict:
    llm = LLM(offline=offline)
    docs, links = load()
    docs.append(doc)
    by_id = {d.doc_id: d for d in docs}
    ext = await PL.extract_doc(llm, doc)
    rejected, repairs = [], []
    new = await PL.verify_doc(llm, doc, ext["rules"], rejected, repairs)
    current = json.loads((ROOT / "out" / "rules.json").read_text(encoding="utf-8"))
    old_rules = current["rules"]
    touched = sorted({c["jurisdiction"] for c in new} | {jurisdiction})
    keep = [r for r in old_rules if r["jurisdiction"] not in touched]
    dropped, discarded, qa = [], [], []
    rebuilt = []
    for j in touched:
        cands = _as_candidates([r for r in old_rules if r["jurisdiction"] == j]) + [c for c in new if c["jurisdiction"] == j]
        ctx = [r for r in old_rules if r["jurisdiction"] == j[-2:]] if len(j) > 2 else \
              [r for r in old_rules if r["jurisdiction"].endswith(", " + j)]
        rs = await PL.consolidate(llm, j, cands, docs, links, ctx, dropped)
        for r in rs:
            if all(c.startswith("existing:") for c in r["from_candidates"]):
                tid = r["from_candidates"][0].split(":", 1)[1]
                rebuilt.append(("keep", next(o for o in old_rules if o["team_rule_id"] == tid)))
                continue
            r["candidate_id"] = r.get("candidate_id") or f"{j}#new"
            jdocs = PL._docs_for(j, [r], docs)
            await PL.audit_coverage(llm, r, jdocs, by_id, discarded)
            await PL.audit_dates(llm, r, jdocs, by_id)
            await PL.legal_qa(llm, r, jdocs, qa)
            rebuilt.append(("new", r))
    fresh = PL.finalize([r for k, r in rebuilt if k == "new"], by_id, old_rules)
    rules = keep + [r for k, r in rebuilt if k == "keep"] + fresh
    rules.sort(key=lambda r: r["team_rule_id"])
    new_ids = {r["team_rule_id"] for r in fresh}

    eff = sorted(r["effective_date"] for r in fresh if r.get("effective_date"))
    pivot = date.fromisoformat(eff[0][:10]) if eff else date.fromisoformat(PL.QUERY_DATE)
    before, after = (pivot - timedelta(days=1)).isoformat(), (pivot + timedelta(days=1)).isoformat()
    test = {"test_id": test_id or "T-new", "jurisdiction": jurisdiction, "doc_id": doc.doc_id,
            "rule_ids": sorted(new_ids), "effective_date": eff[0] if eff else None,
            "as_of_before": before, "as_of_after": after,
            "before": _affected(_engine(rules, before), new_ids), "after": _affected(_engine(rules, after), new_ids)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rules.json").write_text(json.dumps({"rules": rules, "no_rule_findings": current.get("no_rule_findings", [])},
                                                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "change_test.json").write_text(json.dumps(test, indent=2) + "\n", encoding="utf-8")
    (out_dir / "ingest_log.json").write_text(json.dumps({"rejected": rejected, "repairs": repairs, "dropped": dropped,
                                                         "coverage_discarded": discarded, "qa": qa}, indent=2,
                                                        ensure_ascii=False) + "\n", encoding="utf-8")
    return test


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="extraction.ingest_new")
    p.add_argument("--jurisdiction")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", type=Path)
    src.add_argument("--url")
    src.add_argument("--drop", action="store_true", help=f"ingest every file in {DROP}")
    p.add_argument("--test-id")
    p.add_argument("--source-type", default="official")
    p.add_argument("--out-dir", type=Path, default=ROOT / "out_ingest")
    p.add_argument("--offline", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    items = []
    if a.drop:
        for f in sorted(DROP.glob("*.txt")):
            text = f.read_text(encoding="utf-8")
            jur = a.jurisdiction
            if text.startswith("JURISDICTION:"):
                first, _, text = text.partition("\n")
                jur = first.split(":", 1)[1].strip()
            items.append((f"H16-{f.stem}", jur, text, f.as_uri()))
    else:
        if not a.jurisdiction:
            p.error("--jurisdiction is required")
        text = a.file.read_text(encoding="utf-8") if a.file else _fetch(a.url)
        items.append((f"NEW-{(a.file.stem if a.file else 'url')}", a.jurisdiction, text,
                      a.url or a.file.resolve().as_uri()))
    for doc_id, jur, text, url in items:
        jur = normalize_jurisdiction(jur)
        doc = make_doc(doc_id, jur, text, url, a.source_type)
        test = asyncio.run(ingest(doc, jur, a.test_id, a.out_dir, a.offline or None))
        print(json.dumps({k: (v if not isinstance(v, dict) else {r: len(x) for r, x in v.items()})
                          for k, v in test.items()}, indent=2))


if __name__ == "__main__":
    main()
