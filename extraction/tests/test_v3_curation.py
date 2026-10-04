import copy
import json
from pathlib import Path

from extraction.v3 import curation
from extraction.v3.loader import load


ROOT = Path(__file__).resolve().parents[2]


def _rules():
    return copy.deepcopy(json.loads((ROOT / "out" / "rules.json").read_text())["rules"])


def test_evidence_corrections_fill_dates_obligations_and_nj_subsection():
    docs = {d.doc_id: d for d in load()[0]}
    rules = _rules()
    log = curation.apply(rules, docs)
    by_id = {r.get("team_rule_id"): r for r in rules}
    assert by_id["r-0034"]["effective_date"] == "2026-01-01"
    assert by_id["r-0001"]["effective_date"] == "2026-03-01"
    assert by_id["r-0001"]["conflict_flag"] is True
    assert "criminal-history" in by_id["r-0152"]["key_value"]
    assert "statutory good cause" in by_id["r-0108"]["key_value"]
    assert by_id["r-0177"]["key_value"].startswith("Ban on providing or using")
    assert by_id["r-0181"]["key_value"].startswith("Ban on selling")
    assert by_id["r-0165"]["key_value"].startswith("Protected-unit demolition")
    assert any(r["citation"] == "N.J.S.A. 2A:18-61.1(f)" and r["category"] == "rent_increase_limits"
               for r in rules)
    assert any(row["kind"] in {"derived_rule", "date", "key_value"} for row in log)


def test_false_state_preemption_claims_are_removed_but_brief_questions_remain():
    docs = {d.doc_id: d for d in load()[0]}
    rules = _rules()
    curation.apply(rules, docs)
    for r in rules:
        note = r.get("conflict_note") or ""
        assert "1947.9 may preempt" not in note
        assert "1946.2 may preempt" not in note
    assert next(r for r in rules if r.get("team_rule_id") == "r-0001")["conflict_flag"] is True


def test_mangled_false_preemption_residue_is_removed():
    docs = {d.doc_id: d for d in load()[0]}
    rules = _rules()
    target = next(r for r in rules if r.get("team_rule_id") == "r-0069")
    target["conflict_note"] = "A. Mun. Code § 151.09. Cal. Civ. Code § 1947.9 may preempt L.A. Mun. Code § 151.09."
    curation.apply(rules, docs)
    assert target["conflict_note"] is None
    assert target["conflict_flag"] is False


def test_nj_local_rent_rules_receive_the_state_30_year_exemption():
    docs = {d.doc_id: d for d in load()[0]}
    rules = _rules()
    target = next(r for r in rules if r.get("team_rule_id") == "r-0162")
    target["coverage"]["new_construction_exemption"] = None
    target["coverage_evidence"] = [e for e in target.get("coverage_evidence", [])
                                   if e.get("field") != "new_construction_exemption"]
    curation.apply(rules, docs)
    assert target["coverage"]["new_construction_exemption"]["years"] == 30
    assert any(e["field"] == "new_construction_exemption" and e["doc_id"] == "D067"
               for e in target["coverage_evidence"])


def test_statewide_source_income_rule_keeps_general_building_scope():
    docs = {d.doc_id: d for d in load()[0]}
    rules = _rules()
    rules = [r for r in rules if "12955(o)" not in (r.get("citation") or "")]
    curation.apply(rules, docs)
    general = next(r for r in rules if (r.get("citation") or "").endswith("§ 12955"))
    assert general["coverage"]["requires_unknown_facts"] is False
    assert general["coverage_conditions"]["other_conditions"] is None
    assert not any("12955(o)" in (r.get("citation") or "") for r in rules)


def test_sf_relocation_record_states_the_landlord_obligation_with_its_source():
    docs = {d.doc_id: d for d in load()[0]}
    rules = _rules()
    curation.apply(rules, docs)
    r = next(r for r in rules if r.get("citation") == "S.F. Admin. Code § 37.9C")
    assert r["key_value"].startswith("Landlord must pay relocation")
    assert "$8,245.00 per tenant" in r["key_value"]
    assert r["effective_date"] == "2026-03-01"
    assert "Evidence: D083:" in r["effective_date_note"]
