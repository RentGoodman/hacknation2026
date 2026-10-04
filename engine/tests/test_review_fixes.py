from engine.conditions import apply_conditions
from engine.verdict import verdicts_for_building

NO_LINKS = {"supersedes": set(), "conflicts": set(), "uncertain": set()}


def rule(rid, jur, level, cat, cov=None, status="in_force", eff="2000-01-01", **kw):
    return {"team_rule_id": rid, "jurisdiction": jur, "level": level, "category": cat, "status": status,
            "title": rid, "requirement": "x", "coverage_conditions": cov, "overrides": [], "effective_date": eff,
            "citation": rid, "source_url": "u", "quoted_span": "x" * 20, "conflict_flag": False, **kw}


def bldg(state="MA", city="Boston, MA", status="resolved", cand=None, year=1950, units=20, units_min=None):
    return {"state": state, "legal_city": city, "city_status": status, "legal_city_candidate": cand,
            "year_built": year, "units": units, "units_min": units_min, "property_type": None,
            "threshold_year_case": False, "postal_city": "Dorchester"}


def get(b, rules, rid, as_of="2026-10-01", annotations=None):
    return next((e for e in verdicts_for_building(b, rules, as_of, NO_LINKS, annotations=annotations)
                 if e["team_rule_id"] == rid), None)


def test_not_geocoded_city_rule_unknown():
    b = bldg(city=None, status="not_geocoded")
    e = get(b, [rule("c", "Boston, MA", "city", "security_deposits")], "c")
    assert e and e["result"] == "unknown" and "could not be determined" in e["explanation"]


def test_confirmed_other_city_omitted():
    assert get(bldg(), [rule("c", "Cambridge, MA", "city", "security_deposits")], "c") is None


def test_future_rule_with_false_coverage_is_omitted():
    r = rule("f", "MA", "state", "security_deposits", cov={"all": [{"fact": "units", "op": "<", "value": 5}]},
             eff="2030-01-01")
    assert get(bldg(units=20), [r], "f") is None


def test_no_generic_ca_rent_fallback():
    st = rule("s", "CA", "state", "rent_increase_limits")
    ct = rule("c", "San Francisco, CA", "city", "rent_increase_limits")
    e = get(bldg("CA", "San Francisco, CA"), [st, ct], "s")
    assert e["result"] == "applies" and e["conflict_flag"] is False


def test_supersedes_direction_from_interaction():
    cov = {"summary": "x", "construction_date_basis": None, "built_on_or_before": None, "built_after": None,
           "min_building_age_years": None, "min_units": None, "max_units": None,
           "owner_conditions": None, "other_conditions": None}
    st = rule("s", "CA", "state", "rent_increase_limits", cov=cov, overrides=["c"], interaction="Lists local rules.")
    ct = rule("c", "San Francisco, CA", "city", "rent_increase_limits", cov=cov, overrides=["s"],
              interaction="Supersedes s (state cap).")
    b = bldg("CA", "San Francisco, CA")
    assert get(b, [st, ct], "s")["result"] == "superseded"
    assert get(b, [st, ct], "c")["result"] == "applies"


def test_generic_same_category_is_not_a_conflict():
    st = rule("s", "MA", "state", "security_deposits")
    ct = rule("c", "Boston, MA", "city", "security_deposits")
    assert get(bldg(), [st, ct], "s")["conflict_flag"] is False


def test_t3_pair_conflict():
    from engine.precedence import DEFAULT
    st = rule("nj", "NJ", "state", "algorithmic_rent_setting")
    ct = rule("jc", "Jersey City, NJ", "city", "algorithmic_rent_setting")
    b = bldg("NJ", "Jersey City, NJ")
    annotations = {"nj": {**DEFAULT, "may_preempt_local": True}, "jc": DEFAULT}
    assert get(b, [st, ct], "nj", annotations=annotations)["conflict_flag"]
    assert get(b, [st, ct], "jc", annotations=annotations)["conflict_flag"]


def test_links_conflict_and_uncertain():
    a, c = rule("a", "MA", "state", "security_deposits"), rule("b", "Boston, MA", "city", "security_deposits")
    links = {"supersedes": set(), "conflicts": {frozenset(("a", "b"))}, "uncertain": set()}
    es = verdicts_for_building(bldg(), [a, c], "2026-10-01", links)
    assert all(e["conflict_flag"] for e in es)


SMALL_LANDLORD = {"field": "owner_conditions", "effect": "excludes_coverage", "units_max": 4,
                  "label": "small-landlord exception",
                  "text": "Landlord owns no more than two properties with at most four units."}


def test_excludes_coverage_ruled_out_by_units():
    cov, why, notes = apply_conditions(bldg(units=20), [SMALL_LANDLORD], True, None)
    assert cov is True and "cannot apply at 20 units" in notes[0]


def test_excludes_coverage_unknown_when_units_missing():
    cov, why, notes = apply_conditions(bldg(units=None), [SMALL_LANDLORD], True, None)
    assert cov is None and "may apply" in why and "unit count" in why


def test_modifies_terms_keeps_result():
    c = dict(SMALL_LANDLORD, effect="modifies_terms", units_max=None)
    cov, _, notes = apply_conditions(bldg(units=None), [c], True, None)
    assert cov is True and notes


def test_ca_deposit_rule_on_20_units_applies():
    r = rule("dep", "CA", "state", "security_deposits", _conditions=[SMALL_LANDLORD])
    e = get(bldg("CA", "Los Angeles, CA", units=20), [r], "dep")
    assert e["result"] == "applies" and "cannot apply at 20 units" in e["explanation"]


def test_classify_runs_on_rules_with_conditions():
    from engine.classify_conditions import classify
    r = rule("x", "CA", "state", "security_deposits", exemptions="Owner-occupied buildings with 2 or fewer units are exempt.")
    log, _ = classify([r], use_api=False)
    assert r["_conditions"][0]["effect"] == "excludes_coverage" and r["_conditions"][0]["units_max"] is None


def test_facility_exclusion_ruled_out_for_apartment_building():
    c = {"field": "exemptions", "effect": "excludes_coverage", "units_max": None, "label": "care facilities",
         "can_exclude_apartment_building": False, "text": "Medical and detention facilities are excluded."}
    b = dict(bldg(units=None), property_type="multifamily_5plus")
    cov, why, notes = apply_conditions(b, [c], True, None)
    assert cov is True and "unusual situation, not assumed" in notes[0]
    b["property_type"] = None
    assert apply_conditions(b, [c], True, None)[0] is None
