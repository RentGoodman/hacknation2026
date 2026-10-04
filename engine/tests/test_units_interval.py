from engine.conditions import apply_conditions
from engine.verdict import _units, eval_coverage, verdicts_for_building
from engine.voi import compute, missing_fact

NO_LINKS = {"supersedes": set(), "conflicts": set(), "uncertain": set()}


def b(units=None, lo=None, hi=None, **kw):
    d = {"state": "CA", "legal_city": "San Francisco, CA", "city_status": "resolved", "legal_city_candidate": None,
         "year_built": 1950, "units": units, "units_min": lo, "units_max": hi, "property_type": None,
         "threshold_year_case": False}
    d.update(kw)
    return d


def test_interval_decides_true():
    assert _units(b(lo=4, hi=8), ">=", 2) == (True, None)


def test_interval_decides_false():
    assert _units(b(lo=4, hi=8), ">=", 10) == (False, None)
    assert _units(b(lo=4, hi=8), "<", 4) == (False, None)


def test_interval_undecided_names_units():
    r, why = _units(b(lo=4, hi=8), ">=", 5)
    assert r is None and why == "unit count unknown (public record gives 4 to 8 units)"
    r, why = eval_coverage(b(lo=4, hi=8), {"all": [{"fact": "units", "op": ">=", "value": 5}]})
    assert r is None and "4 to 8 units" in why


def test_exact_units_and_lower_bound_only_unchanged():
    assert _units(b(units=6, lo=4, hi=8), ">=", 7) == (False, None)
    assert _units(b(lo=10), ">=", 5) == (True, None)
    assert _units(b(lo=10), "<", 5) == (False, None)
    assert _units(b(lo=3), ">=", 5)[0] is None
    assert _units(b(), ">=", 5) == (None, "unit count is missing")
    assert _units(b(lo=2, hi=4), "in", [2, 3, 4]) == (True, None)


def test_condition_ruled_out_only_by_units_min():
    c = [{"field": "exemptions", "text": "owner-occupied 4 units or fewer", "effect": "excludes_coverage",
          "units_max": 4, "label": "small owner exemption"}]
    cov, _, notes = apply_conditions(b(lo=5, hi=9), c, True, None)
    assert cov is True and "5 to 9 units" in notes[0]
    cov, why, _ = apply_conditions(b(lo=3, hi=9), c, True, None)
    assert cov is None and "small owner exemption" in why


def _rule(rid, jur, level, cov, **kw):
    return {"team_rule_id": rid, "jurisdiction": jur, "level": level, "category": "rent_increase_limits",
            "status": "in_force", "title": f"Rule {rid}", "requirement": "x", "coverage_conditions": cov,
            "overrides": [], "effective_date": "2000-01-01", "citation": rid, "source_url": "u",
            "quoted_span": "x" * 20, "conflict_flag": False, **kw}


def test_state_yields_to_local_with_unknown_coverage():
    st = _rule("st", "CA", "state", None, overrides=["loc"], interaction="Yields to loc where local law applies.")
    loc = _rule("loc", "San Francisco, CA", "city", {"all": [{"fact": "units", "op": ">=", "value": 5}]},
                overrides=["st"])
    out = {e["team_rule_id"]: e for e in verdicts_for_building(b(lo=4, hi=8), [st, loc], "2026-10-01", NO_LINKS)}
    assert out["loc"]["result"] == "unknown"
    assert out["st"]["result"] == "unknown"
    ex = out["st"]["explanation"]
    assert "Yields to Rule loc (loc)" in ex and "unknown" in ex and "4 to 8 units" in ex
    out = {e["team_rule_id"]: e for e in verdicts_for_building(b(units=6), [st, loc], "2026-10-01", NO_LINKS)}
    assert out["st"]["result"] == "superseded"
    out = {e["team_rule_id"]: e for e in verdicts_for_building(b(units=2), [st, loc], "2026-10-01", NO_LINKS)}
    assert out["st"]["result"] == "applies"


def test_voi_grouping():
    assert missing_fact("x (unit count unknown (public record gives 4 to 8 units))") == "units"
    assert missing_fact("small owner exemption not verifiable from the data: ...") == "condition: small owner exemption"
    blds = {"A1": {"legal_city": "Oakland, CA", "normalized_address": "1 A ST"},
            "A2": {"legal_city": "Oakland, CA", "normalized_address": "2 B ST"},
            "A3": {"legal_city": "Berkeley, CA", "normalized_address": "3 C ST"}}
    u = "coverage depends on facts not in the data (unit count is missing)"
    y = "certificate of occupancy date and year built are both missing"
    lk = {"A1": [{"team_rule_id": "r2", "result": "unknown", "explanation": u},
                 {"team_rule_id": "r1", "result": "unknown", "explanation": u},
                 {"team_rule_id": "r3", "result": "applies", "explanation": "ok"}],
          "A2": [{"team_rule_id": "r1", "result": "unknown", "explanation": u}],
          "A3": [{"team_rule_id": "r1", "result": "unknown", "explanation": y},
                 {"team_rule_id": "r4", "result": "unknown", "explanation": y}]}
    rows = compute(lk, blds)
    assert rows[0] == {"missing_fact": "units", "city": "Oakland, CA", "unknown_answers": 3, "buildings": 2,
                       "rules": ["r1", "r2"], "example_address": "1 A ST"}
    assert rows[1]["missing_fact"] == "year_built / certificate_of_occupancy_date"
    assert rows[1]["unknown_answers"] == 2 and rows[1]["buildings"] == 1
    assert len(rows) == 2
