from datetime import date

from engine.coverage_v3 import evaluate, has_v3_coverage, required_unknown_facts


def test_unsupported_neutral_coverage_does_not_block_citywide_rule():
    rule = {"coverage": {"requires_unknown_facts": False},
            "coverage_evidence": [{"field": "requires_unknown_facts", "quoted_span": "supported"}],
            "verification": {"verdicts": {"coverage": "not_supported"}}}
    assert has_v3_coverage(rule)
    verdict, reason, notes = evaluate({}, rule, date(2026, 10, 1))
    assert verdict is True
    assert reason is None
    assert notes == ["Coverage review required."]


def test_unsupported_coverage_without_proved_general_scope_forces_unknown():
    rule = {"coverage": {}, "coverage_evidence": [],
            "verification": {"verdicts": {"coverage": "not_supported"}}}
    assert has_v3_coverage(rule)
    verdict, reason, notes = evaluate({}, rule, date(2026, 10, 1))
    assert verdict is None
    assert "requires review" in reason
    assert notes == ["Coverage review required."]


def test_unsupported_decisive_coverage_keeps_rule_but_forces_unknown():
    rule = {"coverage": {"requires_unknown_facts": True},
            "coverage_evidence": [{"field": "requires_unknown_facts", "quoted_span": "supported"}],
            "verification": {"verdicts": {"coverage": "not_supported"}}}
    assert has_v3_coverage(rule)
    verdict, reason, notes = evaluate({}, rule, date(2026, 10, 1))
    assert verdict is None
    assert "requires review" in reason
    assert notes == ["Coverage review required."]


def test_general_scope_with_unreproduced_exemptions_still_applies_with_review():
    rule = {
        "coverage": {"requires_unknown_facts": False,
                     "unverifiable_exemptions": ["Exempt dwellings are listed in another section"]},
        "coverage_evidence": [
            {"field": "requires_unknown_facts", "doc_id": "D1", "quoted_span": "all residential dwellings"},
            {"field": "unverifiable_exemptions", "doc_id": "D1", "quoted_span": "except exempt dwellings"},
        ],
        "verification": {"verdicts": {"coverage": "not_supported"}},
        "review_note": "The exemptions in § 218-13 were not reproduced in the corpus.",
    }
    verdict, reason, notes = evaluate({}, rule, date(2026, 10, 1))
    assert verdict is True
    assert reason is None
    assert any("§ 218-13" in note for note in notes)
    assert any("review required" in note.lower() for note in notes)


def test_boolean_unknown_scope_gets_named_facts_without_law_specific_ids():
    rule = {
        "coverage": {"requires_unknown_facts": True},
        "coverage_evidence": [{"field": "requires_unknown_facts", "quoted_span": "supported"}],
        "coverage_conditions": {
            "summary": "Applies only to affordable housing decisions in a funded program.",
            "owner_conditions": "The housing provider receives program funding.",
            "other_conditions": None,
        },
    }
    assert required_unknown_facts(rule) == ["program or affordable-housing eligibility"]
    verdict, reason, _ = evaluate({}, rule, date(2026, 10, 1))
    assert verdict is None and reason == "missing facts: program or affordable-housing eligibility"


def test_thirty_year_exemption_waits_for_owner_filing_on_recent_building():
    rule = {
        "coverage": {"new_construction_exemption": {"years": 30, "requires_owner_filing": True}},
        "coverage_evidence": [{"field": "new_construction_exemption", "quoted_span": "supported"}],
    }
    verdict, reason, _ = evaluate({"year_built": 2010}, rule, date(2026, 10, 1))
    assert verdict is None and "only if the owner filed" in reason
    assert evaluate({"year_built": 1980}, rule, date(2026, 10, 1))[0] is True
