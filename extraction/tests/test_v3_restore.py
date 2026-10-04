import asyncio
import copy
import json
from pathlib import Path

from extraction.v3 import pipeline
from extraction.v3.client import LLM
from extraction.v3.loader import load

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "extraction" / "baseline" / "rules_v3_4ea86eb.jsonl"


def _seed_rules():
    rows = [json.loads(line) for line in SEED.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if row.get("_type") != "no_rule_findings"]


def _restore(rules, tmp_path):
    docs, _ = load()
    llm = LLM(offline=True, audit_path=tmp_path / "audit.jsonl")
    return asyncio.run(pipeline.restore_absorbed_citations(llm, rules, docs, {d.doc_id: d for d in docs}))


def test_absorbed_relocation_section_is_restored_from_the_cache(tmp_path):
    restored = _restore(_seed_rules(), tmp_path)
    assert len(restored) == 1
    r = restored[0]
    assert r["jurisdiction"] == "San Francisco, CA"
    assert r["category"] == "just_cause_eviction"
    assert r["citation"] == "S.F. Admin. Code § 37.9C"
    assert r["source_doc_id"] == "D083"
    assert r["quoted_span"] in next(d for d in load()[0] if d.doc_id == "D083").raw
    audit = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert audit and all(row["cache_hit"] for row in audit)


def test_restore_is_skipped_when_the_citation_already_has_its_own_rule(tmp_path):
    rules = _seed_rules()
    sf = next(r for r in rules if r["team_rule_id"] == "r-0126")
    rules.append({**copy.deepcopy(sf), "team_rule_id": "r-9999", "citation": "S.F. Admin. Code § 37.9C"})
    assert _restore(rules, tmp_path) == []


def test_restore_needs_evidence_of_absorption(tmp_path):
    rules = _seed_rules()
    for r in rules:
        r["citation_aliases"] = [a for a in r.get("citation_aliases") or [] if "37.9C" not in a]
    assert _restore(rules, tmp_path) == []
