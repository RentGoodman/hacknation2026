from engine.prepare import prepare_rules
from engine.verdict import verdicts_for_building

AS_OF = "2026-10-01"


def bldg(city="San Francisco, CA", state="CA", year=1926, units=21):
    return {"state": state, "legal_city": city, "city_status": "resolved", "year_built": year, "units": units,
            "units_min": units, "units_max": units, "property_type": "multifamily_5plus", "threshold_year_case": False}


def rule(rid, **kw):
    base = {"team_rule_id": rid, "jurisdiction": "San Francisco, CA", "level": "city",
            "category": "rent_increase_limits", "status": "in_force", "title": f"Rule {rid}",
            "requirement": f"Requirement of {rid}", "key_value": None, "effective_date": "2026-03-01",
            "coverage_conditions": {"construction_date_basis": "certificate_of_occupancy",
                                    "built_on_or_before": "1979-06-13"},
            "exemptions": None, "overrides": [], "interaction": None, "citation": f"Cite {rid}",
            "source_doc_id": "D000", "quoted_span": f"span {rid}", "confidence": 0.9}
    base.update(kw)
    return base


def test_dropped_duplicate_keeps_the_kept_rules_verdict():
    a = rule("x-1", key_value="1.6%", citation="Board announcement", source_doc_id="D080")
    b = rule("x-2", key_value="1.6%", citation="Rent Ordinance", source_doc_id="D081")
    rules, log = prepare_rules([a, b])
    assert len(rules) == 1 and log["canonical_duplicates"]
    for year, expected in ((1926, "applies"), (1990, None)):
        out = {e["team_rule_id"]: e for e in verdicts_for_building(bldg(year=year), rules, AS_OF)}
        got = {k: v["result"] for k, v in out.items()}
        if expected is None:
            assert got == {}
        else:
            assert got == {"x-1": expected, "x-2": expected}
            dropped = [k for k in got if k != rules[0]["team_rule_id"]][0]
            assert "Same obligation as" in out[dropped]["explanation"]


def test_regime_heir_without_year_is_unknown():
    regime = rule("y-1", jurisdiction="Berkeley, CA",
                  coverage_conditions={"construction_date_basis": "certificate_of_occupancy",
                                       "built_on_or_before": "1979-12-31"})
    heir = rule("y-2", jurisdiction="Berkeley, CA", key_value="1.0%", coverage_conditions={"summary": "AGA"})
    rules, _ = prepare_rules([regime, heir])
    b = bldg(city="Berkeley, CA", year=None, units=None)
    out = {e["team_rule_id"]: e["result"] for e in verdicts_for_building(b, rules, AS_OF)}
    assert out["y-2"] == "unknown"


def test_compound_reference_covered_when_any_named_ordinance_covers():
    rso = rule("z-rso", jurisdiction="Los Angeles, CA", title="Rent Stabilization Ordinance (RSO)",
               coverage_conditions={"construction_date_basis": "year_built", "built_on_or_before": "1978-10-01"})
    jco = rule("z-jco", jurisdiction="Los Angeles, CA", category="just_cause_eviction",
               title="Just Cause Ordinance (JCO)", coverage_conditions=None)
    cond = {"field": "other_conditions", "text": "Applies to all RSO and JCO rental units.", "effect": "excludes_coverage",
            "nature": "positive_limit", "situation": "references_coverage", "references": "RSO and JCO",
            "label": "RSO and JCO units", "property_types_targeted": [], "owner_linked": False}
    r = rule("z-1", jurisdiction="Los Angeles, CA", category="just_cause_eviction", coverage_conditions=None,
             _conditions=[cond])
    out = {e["team_rule_id"]: e["result"] for e in
           verdicts_for_building(bldg(city="Los Angeles, CA", year=1990), [rso, jco, r], AS_OF)}
    assert out["z-1"] == "applies"
