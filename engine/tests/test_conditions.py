from engine.conditions import apply_conditions
from engine.verdict import verdicts_for_building

NO_LINKS = {"supersedes": set(), "conflicts": set(), "uncertain": set()}


def rule(rid, jur, level, cat, cov=None, **kw):
    return {"team_rule_id": rid, "jurisdiction": jur, "level": level, "category": cat, "status": "in_force",
            "title": rid, "requirement": "x", "coverage_conditions": cov, "overrides": [], "effective_date": "2000-01-01",
            "citation": rid, "source_url": "u", "quoted_span": "x" * 20, "conflict_flag": False, **kw}


def bldg(**kw):
    b = {"state": "CA", "legal_city": "Los Angeles, CA", "city_status": "resolved", "legal_city_candidate": None,
         "year_built": 1950, "units": 20, "units_min": None, "units_max": None, "property_type": None,
         "threshold_year_case": False}
    return {**b, **kw}


def get(b, rules, rid, as_of="2026-10-01"):
    return next((e for e in verdicts_for_building(b, rules, as_of, NO_LINKS) if e["team_rule_id"] == rid), None)


def cond(**kw):
    return {"field": "exemptions", "effect": "excludes_coverage", "units_max": None, "label": "x", "text": "t", **kw}


SMALL_LANDLORD = cond(field="owner_conditions", units_max=4, label="small-landlord exception",
                      text="Landlord owns no more than two properties with at most four units.")


def test_excludes_coverage_ruled_out_by_units():
    cov, why, notes = apply_conditions(bldg(units=20), [SMALL_LANDLORD], True, None)
    assert cov is True and "small-landlord exception cannot apply at 20 units" in notes[0]


def test_excludes_coverage_unknown_when_units_missing():
    cov, why, notes = apply_conditions(bldg(units=None), [SMALL_LANDLORD], True, None)
    assert cov is None and "not verifiable" in why


def test_modifies_terms_keeps_result():
    c = dict(SMALL_LANDLORD, effect="modifies_terms", units_max=None)
    cov, _, notes = apply_conditions(bldg(units=None), [c], True, None)
    assert cov is True and notes


def test_ca_deposit_rule_on_20_units_applies():
    r = rule("dep", "CA", "state", "security_deposits", _conditions=[SMALL_LANDLORD])
    e = get(bldg(units=20), [r], "dep")
    assert e["result"] == "applies" and "small-landlord exception cannot apply at 20 units" in e["explanation"]


def test_classify_runs_on_rules_with_conditions():
    from engine.classify_conditions import classify
    r = rule("x", "CA", "state", "security_deposits", exemptions="Owner-occupied buildings with 2 or fewer units are exempt.")
    classify([r], use_api=False)
    assert r["_conditions"][0]["effect"] == "excludes_coverage" and r["_conditions"][0]["units_max"] is None


def test_facility_exclusion_ruled_out_for_apartment_building():
    c = cond(label="care facilities", can_exclude_apartment_building=False,
             text="Medical and detention facilities are excluded.")
    b = bldg(units=None, property_type="multifamily_5plus")
    cov, why, notes = apply_conditions(b, [c], True, None)
    assert cov is True and "cannot apply to this building" in notes[0]
    b["property_type"] = None
    assert apply_conditions(b, [c], True, None)[0] is None


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
    assert get(bldg(year_built=1950), [rso, child], "ch")["result"] == "applies"
    assert get(bldg(year_built=2005), [rso, child], "ch") is None


def test_direct_regime_cutoff_wins_over_redundant_unresolved_reference():
    cov = {"summary": "Rent-controlled units", "construction_date_basis": "certificate_of_occupancy",
           "built_on_or_before": "1979-06-13", "built_after": None, "min_building_age_years": None,
           "min_units": None, "max_units": None, "owner_conditions": None,
           "other_conditions": "Applies to units subject to San Francisco rent control."}
    c = cond(situation="references_coverage", references="San Francisco rent control",
             label="Rent-controlled units only")
    r = rule("sf", "San Francisco, CA", "city", "rent_increase_limits", cov, _conditions=[c])
    building = bldg(state="CA", legal_city="San Francisco, CA", year_built=1926)
    assert get(building, [r], "sf")["result"] == "applies"
