import asyncio
import json
from types import SimpleNamespace

from extraction.v3 import pipeline
from extraction.v3.loader import load


def _fake_factory(docs_by_id):
    async def call(self, *, step, subject, prompt, **kw):
        if step == "extract":
            d = docs_by_id[subject]
            span = d.text.strip().splitlines()[5][:80].strip() or d.text[:60]
            rule = {"candidate_id": "c1", "jurisdiction": d.jurisdictions.split(";")[0], "category": "security_deposits",
                    "status": "in_force", "title": "t", "requirement": "r", "key_value": None,
                    "coverage": {"min_units": 2}, "exemptions": None, "event_only": False, "applies_only_in": None,
                    "effective_date": None, "enacted_date": None, "sunset_date": None, "effective_date_note": None,
                    "effective_date_formula": None, "citation": "M.G.L. c. 186, § 15B(1)", "citation_aliases": [],
                    "quoted_span": span, "confidence": 0.9, "conflict_flag": False, "conflict_note": None,
                    "review_note": None}
            bad = {**rule, "candidate_id": "c2", "quoted_span": "this text is not in the document at all zzz"}
            return {"rules": [rule, bad], "no_rule_findings": [], "doc_summary": "s"}
        if step == "recopy":
            return {"spans": []}
        if step == "consolidate":
            cands = json.loads(prompt.split("<candidates>")[1].split("</candidates>")[0])
            return {"rules": [], "dropped_candidates": [], "known_gaps": []} if not cands else {
                "rules": [{**cands[0], "from_candidates": [c["candidate_id"] for c in cands], "also_supported_by": []}],
                "dropped_candidates": [], "known_gaps": []}
        if step == "probe":
            return {"verdicts": []}
        if step == "coverage_audit":
            return {"coverage": {"min_units": 2, "max_units": 9}, "notes": None,
                    "evidence": [{"field": "min_units", "doc_id": "D045", "quoted_span": "not verbatim zzz"}]}
        if step == "date_audit":
            return {"requirement_is_new": None, "in_force_since": None, "in_force_since_evidence": None,
                    "current_version_effective": None, "prior_version_note": None,
                    "effective_date_formula": {"kind": "first_day_of_nth_month_following", "n": 4,
                                               "anchor": "enactment", "anchor_date": "2026-01-15", "verbatim": "x"}}
        if step == "qa":
            return {"changes": [{"field": "status", "after_json": "\"in_force\"", "reason": "same"}]}
        if step == "field_check":
            return {"fields": [{"field": "key_value", "verdict": "not_supported", "quoted_span": None, "note": None},
                               {"field": "citation", "verdict": "supported", "quoted_span": "zzz not there", "note": None}]}
        if step == "plain":
            return {"en": "Deposits are limited.", "es": "Hay 99 reglas."}
        if step == "cell":
            return {"cell_status": "silent", "no_rule_quote": None, "no_rule_passage_id": None,
                    "basis_citation": None, "rules": []}
        return {"replacement": None, "reason": "none"}
    return call


def test_pipeline_end_to_end(monkeypatch, tmp_path):
    docs, _ = load()
    by_id = {d.doc_id: d for d in docs}
    monkeypatch.setattr(pipeline.LLM, "call", _fake_factory(by_id))
    args = SimpleNamespace(concurrency=2, offline=True, docs=["D045", "D046"])
    res = asyncio.run(pipeline.run(args))
    assert res["rules"], "consolidated rules expected"
    r = res["rules"][0]
    assert r["citation"].startswith("G.L. c. 186")
    assert r["effective_date"] == "2026-05-01"
    assert r["coverage"]["max_units"] is None
    assert any(x["candidate_id"].endswith(":c2") for x in res["_rejected"])
    assert r["team_rule_id"].startswith("r-") and r["canonical_id"]
    assert r["verification"]["verdicts"]["citation"] == "partly_supported"
    assert r["plain_language"] == {"en": "Deposits are limited."}
    assert r["found_by"] == ["document"]
    pipeline.write(res, tmp_path)
    assert json.loads((tmp_path / "rules.json").read_text())["rules"]


def test_official_summary_rule_and_unverified_open_questions_are_surfaced():
    docs, _ = load()
    by_id = {d.doc_id: d for d in docs}
    rules = []
    pipeline.add_official_summary_rules(rules, by_id)
    assert {r["source_doc_id"] for r in rules} == {"D078", "DX20", "DX21"}
    sf = next(r for r in rules if r["source_doc_id"] == "D078")
    assert sf["coverage"]["requires_unknown_facts"] is True
    caps = [r for r in rules if r["source_doc_id"] in {"DX20", "DX21"}]
    assert {r["key_value"] for r in caps} == {
        "Lesser of 5% or applicable CPI change; one increase per 12 months",
        "Applicable CPI change, capped at 4% per 12 months",
    }
    assert all(r["coverage"]["new_construction_exemption"]["years"] == 30 for r in caps)
    assert all(r["quoted_span"] in by_id[r["source_doc_id"]].raw for r in caps)

    flagged = [
        {"jurisdiction": "Berkeley, CA", "category": "algorithmic_rent_setting",
         "conflict_flag": False, "conflict_note": None},
        {"jurisdiction": "Los Angeles, CA", "category": "rent_increase_limits",
         "conflict_flag": False, "conflict_note": None},
    ]
    pipeline.surface_organizer_open_questions(flagged)
    assert all(r["conflict_flag"] for r in flagged)
    assert all("not captured" in r["conflict_note"] for r in flagged)


def test_current_records_become_explicit_existing_candidates():
    current = [{"team_rule_id": "r-1", "jurisdiction": "Newark, NJ", "category": "rent_increase_limits",
                "coverage_conditions": {"min_units": 2}, "coverage": {"requires_unknown_facts": False}}]
    candidate = pipeline._current_as_candidates(current)[0]
    assert candidate["candidate_id"] == "existing:r-1"
    assert candidate["coverage"]["min_units"] == 2
    assert candidate["coverage"]["requires_unknown_facts"] is False


def test_no_rule_finding_is_removed_when_curation_adds_an_in_force_rule():
    findings = [{"jurisdiction": "NJ", "category": "rent_increase_limits", "kind": "no_rule",
                 "doc_id": "D067", "quoted_span": "The State of New Jersey has no laws"}]
    rules = [{"jurisdiction": "NJ", "category": "rent_increase_limits", "status": "in_force"}]
    assert pipeline._dedupe_findings(findings, rules) == []


def test_submission_no_rule_findings_exclude_silent_probes_and_require_evidence():
    findings = [
        {"jurisdiction": "Boston, MA", "category": "algorithmic_rent_setting", "kind": "undetermined",
         "doc_id": None, "quoted_span": None, "basis_citation": None, "reason": "silent"},
        {"jurisdiction": "Cambridge, MA", "category": "algorithmic_rent_setting", "kind": "no_rule",
         "doc_id": "DX10", "quoted_span": "Policy language", "basis_citation": None,
         "reason": "no enacted ordinance"},
        {"jurisdiction": "Boston, MA", "category": "rent_increase_limits", "kind": "no_rule",
         "doc_id": "D048", "quoted_span": "No city or town may enact rent control",
         "basis_citation": "G.L. c. 40P, § 4", "reason": "state bar"},
    ]
    assert pipeline._dedupe_findings(findings, []) == [{
        "jurisdiction": "Boston, MA", "category": "rent_increase_limits",
        "citation": "G.L. c. 40P, § 4", "quoted_span": "No city or town may enact rent control",
         "reason": "state bar", "source_doc_id": "D048",
     }]
