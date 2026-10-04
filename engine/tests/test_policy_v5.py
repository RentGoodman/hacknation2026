from engine.conditions import apply_conditions
from buildings.api import check_record
from engine.verdict import _co_date, _year_built, verdicts_for_building

NO_LINKS = {"supersedes": set(), "conflicts": set(), "uncertain": set()}


def rule(rid, jur, level, cat, cov=None, **kw):
    return {"team_rule_id": rid, "jurisdiction": jur, "level": level, "category": cat, "status": "in_force",
            "title": rid, "requirement": "x", "coverage_conditions": cov, "overrides": [], "effective_date": "2000-01-01",
            "citation": rid, "source_url": "u", "quoted_span": "x" * 20, "conflict_flag": False, **kw}


def bldg(**kw):
    b = {"state": "CA", "legal_city": "San Diego, CA", "city_status": "resolved", "legal_city_candidate": None,
         "year_built": 1950, "units": 20, "units_min": 20, "units_max": 20, "property_type": "multifamily_5plus",
         "threshold_year_case": False}
    return {**b, **kw}


def get(b, rules, rid, as_of="2026-10-01"):
    return next((e for e in verdicts_for_building(b, rules, as_of, NO_LINKS) if e["team_rule_id"] == rid), None)


def test_postal_fallback_city_rule_unknown_never_applies():
    b = bldg(city_status="postal_fallback")
    e = get(b, [rule("sd", "San Diego, CA", "city", "just_cause_eviction")], "sd")
    assert e["result"] == "unknown" and "postal city only" in e["explanation"]
    assert get(b, [rule("st", "CA", "state", "just_cause_eviction")], "st")["result"] == "applies"


def test_co_interval_kleene():
    assert _co_date(bldg(year_built=1950), "<=", "1979-06-13") == (True, None)
    assert _co_date(bldg(year_built=1990), "<=", "1979-06-13") == (False, None)
    v, why = _co_date(bldg(year_built=None, co_date_min="1979-01-01", co_date_max="1979-12-31"), "<=", "1979-06-13")
    assert v is None and "between 1979-01-01 and 1979-12-31" in why
    assert _co_date(bldg(year_built=None, co_date_min="1979-01-01", co_date_max="1979-03-01"), "<=", "1979-06-13")[0] is True


def test_one_sided_public_year_and_co_bounds_are_used():
    upper = bldg(year_built=None, year_built_max=1985, co_date_min=None, co_date_max="1985-12-31")
    assert _year_built(upper, "<=", 1990) == (True, None)
    assert _year_built(upper, ">", 1990) == (False, None)
    assert _year_built(upper, "<=", 1980)[0] is None
    assert _co_date(upper, "<=", "1990-01-01") == (True, None)
    assert _co_date(upper, ">", "1990-01-01") == (False, None)
    assert _co_date(upper, "<=", "1980-01-01")[0] is None


def test_public_api_and_engine_agree_on_bounded_construction_facts():
    records = [
        bldg(year_built=1979, year_built_max=1979,
             co_date_min="1979-01-01", co_date_max="1979-12-31"),
        bldg(year_built=None, year_built_max=1985,
             co_date_min=None, co_date_max="1985-12-31"),
        bldg(year_built=None, year_built_max=None, co_date_min=None, co_date_max=None),
    ]
    decode = {"true": True, "false": False, "unknown": None}
    for record in records:
        for op, value in (("<=", 1980), (">", 1990), ("==", 1979), ("in", [1979, 1985])):
            assert decode[check_record(record, "year_built", op, value)] is _year_built(record, op, value)[0]
        for op, value in (("<=", "1980-01-01"), (">", "1990-01-01"),
                          ("==", "1979-06-13"), ("in", ["1979-01-01", "1985-12-31"])):
            assert decode[check_record(record, "certificate_of_occupancy_date", op, value)] is \
                _co_date(record, op, value)[0]


def cond(**kw):
    return {"field": "exemptions", "effect": "excludes_coverage", "units_max": None, "label": "x", "text": "t", **kw}


def test_unusual_situation_exemption_keeps_applies_and_names_it():
    c = cond(situation="unusual", label="seasonal rental exemption", text="Seasonal rentals are exempt.")
    cov, why, notes = apply_conditions(bldg(), [c], True, None)
    assert cov is True and "seasonal rental exemption" in notes[0]


def test_restricted_positive_coverage_stays_unknown():
    c = cond(situation="restricted_coverage", label="affordable housing only", text="Only affordable units.")
    cov, why, _ = apply_conditions(bldg(), [c], True, None)
    assert cov is None and "affordable housing only" in why


def test_reference_to_other_ordinance_coverage():
    rso = rule("rso", "Los Angeles, CA", "city", "rent_increase_limits",
               {"summary": "RSO", "construction_date_basis": "certificate_of_occupancy",
                "built_on_or_before": "1978-10-01", "built_after": None, "min_building_age_years": None,
                "min_units": None, "max_units": None, "owner_conditions": None, "other_conditions": None},
               title="Los Angeles Rent Stabilization Ordinance (RSO)")
    c = cond(situation="references_coverage", references="Rent Stabilization Ordinance", label="must be RSO-covered")
    child = rule("ch", "Los Angeles, CA", "city", "just_cause_eviction", _conditions=[c])
    old, new = bldg(legal_city="Los Angeles, CA", year_built=1950), bldg(legal_city="Los Angeles, CA", year_built=2005)
    assert get(old, [rso, child], "ch")["result"] == "applies"
    assert get(new, [rso, child], "ch") is None
