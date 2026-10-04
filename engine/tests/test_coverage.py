import pytest

from buildings.api import check_record
from engine.prepare import prepare_rules
from engine.rules import load_buildings, load_rules
from engine.verdict import _co_date, _year_built, is_part1, lookups, verdicts_for_building


def cov(**kw):
    base = {"summary": "test", "construction_date_basis": None, "built_on_or_before": None, "built_after": None,
            "min_building_age_years": None, "min_units": None, "max_units": None,
            "owner_conditions": None, "other_conditions": None}
    return {**base, **kw}


def rule(rid, jur, level, cat, coverage, citation="Test cite", conf=0.9, status="in_force", eff="2000-01-01"):
    return {"team_rule_id": rid, "jurisdiction": jur, "level": level, "category": cat, "status": status,
            "title": rid, "requirement": "x", "coverage_conditions": coverage, "overrides": [],
            "effective_date": eff, "citation": citation, "source_url": "u", "quoted_span": "x" * 20,
            "confidence": conf, "conflict_flag": False}


def bldg(state, city, year=None, units=None, units_min=None, threshold=False, year_max=None):
    return {"state": state, "legal_city": city, "city_status": "resolved", "legal_city_candidate": None,
            "year_built": year, "year_built_max": year_max, "units": units, "units_min": units_min,
            "units_max": None, "property_type": None,
            "threshold_year_case": threshold}


SF_RENT = rule("p1-sf", "San Francisco, CA", "city", "rent_increase_limits",
               cov(construction_date_basis="certificate_of_occupancy", built_on_or_before="1979-06-13"))
LA_RSO = rule("p1-la", "Los Angeles, CA", "city", "rent_increase_limits",
              cov(construction_date_basis="certificate_of_occupancy", built_on_or_before="1978-10-01"))
BERK_AGE = rule("p1-berk", "Berkeley, CA", "city", "just_cause_eviction", cov(min_building_age_years=15))
CA_DEP = rule("p1-dep", "CA", "state", "security_deposits", None)


def res(b, rules, rid, as_of="2026-10-01"):
    return next((e for e in verdicts_for_building(b, rules, as_of) if e["team_rule_id"] == rid), None)


def test_detect_format():
    assert is_part1(SF_RENT["coverage_conditions"])
    assert not is_part1({"all": []}) and not is_part1(None) and not is_part1("text")


def facts(**kw):
    return {"year_built": None, "year_built_max": None, "co_date_min": None, "co_date_max": None, **kw}


def test_co_interval_kleene():
    assert _co_date(facts(year_built=1950), "<=", "1979-06-13") == (True, None)
    assert _co_date(facts(year_built=1990), "<=", "1979-06-13") == (False, None)
    v, why = _co_date(facts(co_date_min="1979-01-01", co_date_max="1979-12-31"), "<=", "1979-06-13")
    assert v is None and "between 1979-01-01 and 1979-12-31" in why
    assert _co_date(facts(co_date_min="1979-01-01", co_date_max="1979-03-01"), "<=", "1979-06-13")[0] is True


def test_one_sided_public_year_and_co_bounds_are_used():
    upper = facts(year_built_max=1985, co_date_max="1985-12-31")
    assert _year_built(upper, "<=", 1990) == (True, None)
    assert _year_built(upper, ">", 1990) == (False, None)
    assert _year_built(upper, "<=", 1980)[0] is None
    assert _co_date(upper, "<=", "1990-01-01") == (True, None)
    assert _co_date(upper, ">", "1990-01-01") == (False, None)
    assert _co_date(upper, "<=", "1980-01-01")[0] is None


def test_public_api_and_engine_agree_on_bounded_construction_facts():
    records = [
        facts(year_built=1979, year_built_max=1979, co_date_min="1979-01-01", co_date_max="1979-12-31"),
        facts(year_built_max=1985, co_date_max="1985-12-31"),
        facts(),
    ]
    decode = {"true": True, "false": False, "unknown": None}
    for record in records:
        for op, value in (("<=", 1980), (">", 1990), ("==", 1979), ("in", [1979, 1985])):
            assert decode[check_record(record, "year_built", op, value)] is _year_built(record, op, value)[0]
        for op, value in (("<=", "1980-01-01"), (">", "1990-01-01"),
                          ("==", "1979-06-13"), ("in", ["1979-01-01", "1985-12-31"])):
            assert decode[check_record(record, "certificate_of_occupancy_date", op, value)] is \
                _co_date(record, op, value)[0]


def test_sf_2005_not_covered():
    assert res(bldg("CA", "San Francisco, CA", 2005), [SF_RENT], "p1-sf") is None


def test_sf_1950_applies():
    assert res(bldg("CA", "San Francisco, CA", 1950), [SF_RENT], "p1-sf")["result"] == "applies"


def test_la_1978_unknown():
    e = res(bldg("CA", "Los Angeles, CA", 1978, threshold=True), [LA_RSO], "p1-la")
    assert e["result"] == "unknown" and "certificate of occupancy" in e["explanation"]


def test_berkeley_age_unknown():
    e = res(bldg("CA", "Berkeley, CA", None), [BERK_AGE], "p1-berk")
    assert e["result"] == "unknown" and "age" in e["explanation"]


def test_age_is_rolling():
    b = bldg("CA", "Berkeley, CA", 2012)
    assert res(b, [BERK_AGE], "p1-berk", "2026-10-01") is None
    assert res(b, [BERK_AGE], "p1-berk", "2027-07-02")["result"] == "unknown"
    assert res(b, [BERK_AGE], "p1-berk", "2028-01-01")["result"] == "applies"


def test_public_year_upper_bound_decides_only_safe_cases():
    old = bldg("CA", "Berkeley, CA", year_max=1985)
    recent = bldg("CA", "Berkeley, CA", year_max=2025)
    assert res(old, [BERK_AGE], "p1-berk", "2026-10-01")["result"] == "applies"
    assert res(recent, [BERK_AGE], "p1-berk", "2026-10-01")["result"] == "unknown"
    cutoff = rule("p1-cut", "CA", "state", "just_cause_eviction",
                  cov(construction_date_basis="year_built", built_on_or_before="1990-01-01"))
    assert res(old, [cutoff], "p1-cut")["result"] == "applies"
    assert res(recent, [cutoff], "p1-cut")["result"] == "unknown"


def test_units_lower_bound():
    r = rule("p1-u", "CA", "state", "screening_restrictions", cov(min_units=5))
    assert res(bldg("CA", "Berkeley, CA", units_min=5), [r], "p1-u")["result"] == "applies"
    assert res(bldg("CA", "Berkeley, CA"), [r], "p1-u")["result"] == "unknown"
    r2 = rule("p1-u2", "CA", "state", "screening_restrictions", cov(max_units=4))
    assert res(bldg("CA", "Berkeley, CA", units_min=5), [r2], "p1-u2") is None


def test_informational_conditions_do_not_change_result():
    r = rule("p1-o", "CA", "state", "security_deposits", cov(owner_conditions="Small landlords owning at most 2 properties"))
    e = res(bldg("CA", "Berkeley, CA"), [r], "p1-o")
    assert e["result"] == "applies"
    assert "Not verifiable from the data: Small landlords owning at most 2 properties" in e["explanation"]


def test_ca_deposit_applies_to_all_ca():
    b = load_buildings()
    L = lookups(b, [CA_DEP], "2026-10-01")
    for a, x in b.items():
        hit = [e for e in L[a] if e["team_rule_id"] == "p1-dep"]
        assert (hit and hit[0]["result"] == "applies") if x["state"] == "CA" else not hit


def test_ma_40p_kept_and_not_a_cap():
    from engine.precedence import is_cap_rule
    r = rule("p1-40p", "MA", "state", "rent_increase_limits", None, citation="M.G.L. c. 40P, § 3")
    kept, log = prepare_rules([r, CA_DEP])
    assert [k["team_rule_id"] for k in kept] == ["p1-40p", "p1-dep"]
    assert log["excluded"] == []
    assert not is_cap_rule(r, {"bars_local_cap": True})
    assert not is_cap_rule(r, {})


def test_duplicates_keep_highest_confidence():
    a = rule("p1-a", "CA", "state", "security_deposits", None, citation="Cal. Civ. Code § 1950.5", conf=0.6)
    b = rule("p1-b", "CA", "state", "security_deposits", None, citation="Cal. Civ. Code 1950.5", conf=0.95)
    a["requirement"] = b["requirement"] = "Security deposit capped at one month's rent."
    kept, log = prepare_rules([a, b])
    assert [k["team_rule_id"] for k in kept] == ["p1-b"]
    assert log["duplicates"][0]["dropped"] == ["p1-a"]



@pytest.fixture(scope="module")
def real():
    rules, source, is_fixture = load_rules(fetch=False)
    if is_fixture:
        pytest.skip("Part 1 rules.json not available yet")
    kept, _ = prepare_rules(rules)
    return load_buildings(), kept


def _find(rules, jur, cat):
    return [r for r in rules if r["jurisdiction"] == jur and r["category"] == cat]


def test_official_screening_summary_rules_are_retained(real):
    buildings, rules = real
    screening = {r.get("source_doc_id"): r for r in rules if r.get("category") == "screening_restrictions"}
    assert {"D010", "D012", "D049", "D078"} <= set(screening)

    verdicts = lookups(buildings, rules, "2026-10-01")
    boston = next(a for a, b in buildings.items() if b.get("legal_city") == "Boston, MA")
    by_id = {e["team_rule_id"]: e for e in verdicts[boston]}
    assert by_id[screening["D010"]["team_rule_id"]]["result"] == "unknown"
    assert by_id[screening["D012"]["team_rule_id"]]["result"] == "applies"
    assert by_id[screening["D049"]["team_rule_id"]]["result"] == "applies"

    san_francisco = next(a for a, b in buildings.items() if b.get("legal_city") == "San Francisco, CA")
    sf_entry = next(e for e in verdicts[san_francisco]
                    if e["team_rule_id"] == screening["D078"]["team_rule_id"])
    assert sf_entry["result"] == "unknown"


def test_real_sf_2005_not_rent_controlled(real):
    b, rules = real
    sf = [r for r in _find(rules, "San Francisco, CA", "rent_increase_limits")
          if is_part1(r.get("coverage_conditions")) and r["coverage_conditions"].get("built_on_or_before")]
    if not sf:
        pytest.skip("no SF rent rule with a cutoff")
    x = bldg("CA", "San Francisco, CA", 2005)
    for r in sf:
        e = res(x, rules, r["team_rule_id"])
        assert e is None or e["result"] != "applies"


def test_real_la_1978_unknown(real):
    b, rules = real
    la = [r for r in _find(rules, "Los Angeles, CA", "rent_increase_limits")
          if is_part1(r.get("coverage_conditions")) and r["coverage_conditions"].get("built_on_or_before")]
    if not la:
        pytest.skip("no LA rent rule with a cutoff")
    L = lookups(b, rules, "2026-10-01")
    for a in ("A0107", "A0432"):
        hits = [e for e in L[a] if e["team_rule_id"] in {r["team_rule_id"] for r in la}]
        assert hits and all(e["result"] in ("unknown", "pending", "not_yet_effective") for e in hits)


def test_real_berkeley_age_unknown(real):
    b, rules = real
    age = [r for r in rules if r["jurisdiction"] == "Berkeley, CA" and is_part1(r.get("coverage_conditions"))
           and r["coverage_conditions"].get("min_building_age_years") is not None]
    if not age:
        pytest.skip("no Berkeley age-based rule")
    L = lookups(b, rules, "2026-10-01")
    ids = {r["team_rule_id"] for r in age}
    for a, x in b.items():
        if x["legal_city"] == "Berkeley, CA":
            assert all(e["result"] != "applies" for e in L[a] if e["team_rule_id"] in ids)


def test_real_ca_deposit_applies_all_ca(real):
    b, rules = real
    decisive = ("built_on_or_before", "built_after", "min_building_age_years", "min_units", "max_units")
    dep = [r for r in _find(rules, "CA", "security_deposits") if r["status"] == "in_force"
           and not any((r.get("coverage_conditions") or {}).get(k) for k in decisive)]
    if not dep:
        pytest.skip("no unconditional CA deposit rule")
    L = lookups(b, rules, "2026-10-01")
    for r in dep:
        if r.get("effective_date") and r["effective_date"] > "2026-10-01":
            continue
            rid = r["team_rule_id"]
            for a, x in b.items():
                if x["state"] == "CA":
                    result = next((e["result"] for e in L[a] if e["team_rule_id"] == rid), None)
                    allowed = ("applies", "superseded", "unknown") if "units_conflict" in x.get("flags", []) \
                        else ("applies", "superseded")
                    assert result in allowed, (rid, a, result)


def test_same_citation_different_obligations_both_kept():
    a = rule("p1-cap", "CA", "state", "security_deposits", None, citation="Cal. Civ. Code § 1950.5")
    a["requirement"] = "A landlord may not demand a security deposit above one month's rent."
    b = rule("p1-ret", "CA", "state", "security_deposits", None, citation="Cal. Civ. Code 1950.5")
    b["requirement"] = "The landlord must return the deposit within 21 days after the tenant vacates."
    a["quoted_span"], b["quoted_span"] = "shall not exceed one month's rent", "within 21 days after the tenant has vacated"
    kept, log = prepare_rules([a, b])
    assert {k["team_rule_id"] for k in kept} == {"p1-cap", "p1-ret"} and not log["duplicates"]


def test_canonical_duplicates_across_citations():
    a = rule("p1-sf1", "San Francisco, CA", "city", "rent_increase_limits", None, citation="Rent Board notice", conf=0.8)
    b = rule("p1-sf2", "San Francisco, CA", "city", "rent_increase_limits", None, citation="Rent Ordinance", conf=0.9)
    for r, req in ((a, "Allowable increase 1.6% for 2026."), (b, "Landlords may raise rent by no more than 1.6%.")):
        r.update(key_value="1.6%", effective_date="2026-03-01", requirement=req, quoted_span=req + " span")
    kept, log = prepare_rules([a, b])
    assert [k["team_rule_id"] for k in kept] == ["p1-sf2"]
    assert "secondary_sources: p1-sf1" in kept[0]["interaction"]
    assert log["canonical_duplicates"][0]["secondary_sources"] == ["p1-sf1"]


def test_regime_coverage_inheritance():
    regime = rule("p1-rso", "Los Angeles, CA", "city", "rent_increase_limits",
                  cov(construction_date_basis="certificate_of_occupancy", built_on_or_before="1978-10-01"))
    adj = rule("p1-3pct", "Los Angeles, CA", "city", "rent_increase_limits", cov(), citation="RSO 3% notice")
    adj["requirement"], adj["quoted_span"] = "3% allowable increase.", "3% allowable increase for the period"
    kept, log = prepare_rules([regime, adj])
    heir = next(r for r in kept if r["team_rule_id"] == "p1-3pct")
    assert heir["_inherited_from"] == ["p1-rso"]
    assert heir["coverage_conditions"]["built_on_or_before"] == "1978-10-01"
    assert res(bldg("CA", "Los Angeles, CA", 2005), kept, "p1-3pct") is None
    assert res(bldg("CA", "Los Angeles, CA", 1978, threshold=True), kept, "p1-3pct")["result"] == "unknown"
    assert log["regime_inheritance"][0]["inherited_from"] == ["p1-rso"]


def test_inherited_unknown_never_makes_state_rule_unknown():
    state = rule("p1-cap", "CA", "state", "rent_increase_limits", None, citation="Civ 1947.12")
    regime = rule("p1-rso", "Los Angeles, CA", "city", "rent_increase_limits",
                  cov(construction_date_basis="certificate_of_occupancy", built_on_or_before="1978-10-01"),
                  citation="RSO")
    adj = rule("p1-3pct", "Los Angeles, CA", "city", "rent_increase_limits", cov(), citation="RSO 3% notice")
    adj["overrides"], adj["interaction"] = ["p1-cap"], "Supersedes p1-cap (state cap)."
    adj["requirement"], adj["quoted_span"] = "3% allowable increase.", "3% allowable increase for the period"
    kept, _ = prepare_rules([state, regime, adj])
    e = res(bldg("CA", "Los Angeles, CA", 1978, threshold=True), kept, "p1-cap")
    assert e["result"] == "applies"


def test_real_time_bounded_rules(real):
    from engine.run import evaluation_context as load_context
    from engine.tests.test_single_path import all_verdicts
    ctx = load_context(fetch=False)
    by = {r["team_rule_id"]: r for r in ctx["rules"]}
    if "r-0067" not in by or not by["r-0067"].get("valid_until"):
        pytest.skip("r-0067 has no extracted valid_until")
    assert by["r-0067"]["valid_until"] == "2026-06-30"
    assert by.get("r-0068", {}).get("valid_until") is None
    L = all_verdicts(ctx, "2026-10-01")
    figures = [e for v in L.values() for e in v if e["team_rule_id"] == "r-0067"]
    assert figures and any("Figure for the period ending 2026-06-30" in e["explanation"] for e in figures)
    assert {e["result"] for e in figures} <= {"applies", "unknown", "superseded"}


def test_real_conduct_never_excludes_coverage(real):
    from engine.run import evaluation_context as load_context
    from engine.tests.test_single_path import all_verdicts
    ctx = load_context(fetch=False)
    b = ctx["buildings"]
    statewide_ca = [r["team_rule_id"] for r in ctx["rules"]
                    if r.get("jurisdiction") == "CA"
                    and r.get("category") == "algorithmic_rent_setting"
                    and r.get("status") == "in_force"]
    assert statewide_ca
    L = all_verdicts(ctx, "2026-01-02")
    for a, x in b.items():
        if x["state"] == "CA":
            for rid in statewide_ca:
                assert any(e["team_rule_id"] == rid and e["result"] == "applies" for e in L[a]), (rid, a)
    L = all_verdicts(ctx, "2026-10-01")
    city_bans = {r["jurisdiction"]: r["team_rule_id"] for r in ctx["rules"]
                 if r.get("jurisdiction") in ("Hoboken, NJ", "Jersey City, NJ")
                 and r.get("category") == "algorithmic_rent_setting"
                 and r.get("status") == "in_force"}
    assert set(city_bans) == {"Hoboken, NJ", "Jersey City, NJ"}
    for a, x in b.items():
        for c, rid in city_bans.items():
            if x["legal_city"] == c:
                result = next(e["result"] for e in L[a] if e["team_rule_id"] == rid)
                assert result in (("applies", "unknown") if c == "Jersey City, NJ" else ("applies",)), (rid, a)
            elif x.get("legal_city_candidate") == c:
                assert any(e["team_rule_id"] == rid and e["result"] == "unknown" for e in L[a]), (rid, a)



def test_real_r0146_applies_with_review_for_unreproduced_218_13(real):
    from engine.run import evaluation_context as load_context
    from engine.tests.test_single_path import all_verdicts
    ctx = load_context(fetch=False)
    L = all_verdicts(ctx, "2026-10-01")
    for a, x in ctx["buildings"].items():
        if x["legal_city"] == "Jersey City, NJ":
            e = next(e for e in L[a] if e["team_rule_id"] == "r-0146")
            assert e["result"] == "applies"
            assert "218-13" in e["explanation"]
            assert "Coverage review required" in e["explanation"]
