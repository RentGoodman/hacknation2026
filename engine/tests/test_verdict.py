import copy
import json
from pathlib import Path

import pytest

from engine.rules import load_buildings
from engine.verdict import eval_coverage, lookups, verdicts_for_building

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "dev_rules.json"
RULES = json.loads(FIXTURE.read_text())["rules"]
AS_OF = "2026-10-01"


def bldg(state, city=None, year=1950, units=10, units_min=None, status="resolved", candidate=None,
         threshold=False, ptype="multifamily_5plus"):
    return {"state": state, "legal_city": city, "city_status": status, "legal_city_candidate": candidate,
            "year_built": year, "units": units, "units_min": units_min, "property_type": ptype,
            "threshold_year_case": threshold}


def entries(b, as_of=AS_OF, rules=RULES, annotations=None):
    return {e["team_rule_id"]: e for e in verdicts_for_building(b, rules, as_of, annotations=annotations)}


NO_LINKS = {"supersedes": set(), "conflicts": set(), "uncertain": set()}


def rule(rid, jur, level, cat, cov=None, eff="2000-01-01", **kw):
    return {"team_rule_id": rid, "jurisdiction": jur, "level": level, "category": cat, "status": "in_force",
            "title": rid, "requirement": "x", "coverage_conditions": cov, "overrides": [], "effective_date": eff,
            "citation": rid, "source_url": "u", "quoted_span": "x" * 20, "conflict_flag": False, **kw}


def one(b, rules, rid, as_of=AS_OF, links=NO_LINKS):
    return next((e for e in verdicts_for_building(b, rules, as_of, links) if e["team_rule_id"] == rid), None)


@pytest.fixture(scope="module")
def buildings():
    return load_buildings()



def test_lookups_cover_all_ids(buildings):
    out = lookups(buildings, RULES, AS_OF)
    assert set(out) == set(buildings)
    assert len(out) == 500


@pytest.mark.parametrize("as_of", ["2026-10-01", "2030-01-01"])
def test_pending_never_applies_failed_never_appears(buildings, as_of):
    out = lookups(buildings, RULES, as_of)
    for aid, es in out.items():
        for e in es:
            assert e["team_rule_id"] != "dev-ma-ballot", aid
            if e["team_rule_id"].startswith("dev-ma-"):
                assert e["result"] != "applies", (aid, e)


def test_boston_cambridge_no_rent_limits(buildings):
    out = lookups(buildings, RULES, AS_OF)
    cat = {r["team_rule_id"]: r["category"] for r in RULES}
    hits = [aid for aid, b in buildings.items()
            if (b.get("legal_city") or b.get("legal_city_candidate") or "") in ("Boston, MA", "Cambridge, MA")]
    for aid in hits:
        assert not [e for e in out[aid] if cat[e["team_rule_id"]] == "rent_increase_limits"], aid


def test_boston_cambridge_hand_built():
    for c in ("Boston, MA", "Cambridge, MA"):
        es = entries(bldg("MA", c))
        assert "dev-ma-ballot" not in es
        assert all(rid.startswith("dev-ma-") and e["result"] == "pending" for rid, e in es.items())



def test_postal_only_jersey_city_unknown():
    b = bldg("NJ", None, status="postal_only", candidate="Jersey City, NJ")
    e = entries(b)["dev-jc-alg"]
    assert e["result"] == "unknown"
    assert "not confirmed" in e["explanation"]


def test_not_geocoded_city_rule_unknown():
    e = one(bldg("MA", None, status="not_geocoded"), [rule("c", "Boston, MA", "city", "security_deposits")], "c")
    assert e and e["result"] == "unknown" and "could not be determined" in e["explanation"]


def test_postal_fallback_city_rule_unknown_never_applies():
    b = bldg("CA", "San Diego, CA", status="postal_fallback")
    e = one(b, [rule("sd", "San Diego, CA", "city", "just_cause_eviction")], "sd")
    assert e["result"] == "unknown" and "postal city only" in e["explanation"]
    assert one(b, [rule("st", "CA", "state", "just_cause_eviction")], "st")["result"] == "applies"


def test_confirmed_other_city_omitted():
    assert one(bldg("MA", "Boston, MA"), [rule("c", "Cambridge, MA", "city", "security_deposits")], "c") is None



def test_la_threshold_1978_unknown():
    e = entries(bldg("CA", "Los Angeles, CA", year=1978, threshold=True))["dev-la-rso"]
    assert e["result"] == "unknown"
    assert "certificate of occupancy" in e["explanation"]


def test_sf_threshold_1979_unknown():
    e = entries(bldg("CA", "San Francisco, CA", year=1979, threshold=True))["dev-sf-rent"]
    assert e["result"] == "unknown"
    assert "certificate of occupancy" in e["explanation"]



def test_nj_fair_not_yet_then_applies():
    b = bldg("NJ", "Newark, NJ")
    assert entries(b, "2026-10-01")["dev-nj-fair"]["result"] == "not_yet_effective"
    e = entries(b, "2027-07-02")["dev-nj-fair"]
    assert e["result"] == "applies"
    assert e["conflict_flag"] is False


def test_nj_fair_conflict_with_jersey_city():
    from engine.precedence import DEFAULT
    b = bldg("NJ", "Jersey City, NJ")
    annotations = {r["team_rule_id"]: {**DEFAULT, "may_preempt_local": r["team_rule_id"] == "dev-nj-fair"}
                   for r in RULES}
    later = entries(b, "2027-07-02", annotations=annotations)
    assert later["dev-nj-fair"]["conflict_flag"] is True
    assert later["dev-jc-alg"]["conflict_flag"] is True
    now = entries(b, "2026-10-01", annotations=annotations)
    assert now["dev-nj-fair"]["conflict_flag"] is False
    assert now["dev-jc-alg"]["conflict_flag"] is False


def test_fair_preemption_conflict_type_is_relational():
    fair = rule("fair", "NJ", "state", "algorithmic_rent_setting", conflict_type="preemption")
    jc = rule("jc", "Jersey City, NJ", "city", "algorithmic_rent_setting")
    hob = rule("hob", "Hoboken, NJ", "city", "algorithmic_rent_setting")
    rules = [fair, jc, hob]
    for city in ("Jersey City, NJ", "Hoboken, NJ"):
        e = one(bldg("NJ", city), rules, "fair")
        assert e["conflict_flag"] is True, city
        assert "Part 1 conflict classification: preemption" in e["explanation"]
    e = one(bldg("NJ", "Newark, NJ"), rules, "fair")
    assert e["result"] == "applies"
    assert e["conflict_flag"] is False
    assert "Part 1 conflict classification" not in e["explanation"]


def test_verdict_has_no_hard_coded_legal_cases():
    import re
    import engine.verdict
    src = Path(engine.verdict.__file__).read_text()
    for token in (r"\bNJ\b", r"algorithmic_rent_setting", r"40P"):
        assert not re.search(token, src), token


def test_ca_alg_effective_boundary():
    b = bldg("CA", "Fresno, CA")
    assert entries(b, "2025-12-31")["dev-ca-alg"]["result"] == "not_yet_effective"
    assert entries(b, "2026-01-02")["dev-ca-alg"]["result"] == "applies"


def test_future_rule_with_false_coverage_is_omitted():
    r = rule("f", "MA", "state", "security_deposits", {"all": [{"fact": "units", "op": "<", "value": 5}]},
             eff="2030-01-01")
    assert one(bldg("MA", "Boston, MA", units=20), [r], "f") is None



UNITS5 = {"all": [{"fact": "units", "op": ">=", "value": 5}]}


def test_units_lower_bound_satisfies():
    assert eval_coverage(bldg("CA", units=None, units_min=5), UNITS5) == (True, None)


def test_units_missing_unknown():
    r, why = eval_coverage(bldg("CA", units=None, units_min=None), UNITS5)
    assert r is None and "unit count" in why


def test_free_text_coverage_unknown():
    rule = dict(RULES[0], team_rule_id="t-free", coverage_conditions="buildings with 5+ units built before 1995")
    e = entries(bldg("CA", "Fresno, CA"), rules=[rule])["t-free"]
    assert e["result"] == "unknown" and "not machine readable" in e["explanation"]


def test_false_coverage_omitted():
    rule = dict(RULES[0], team_rule_id="t-false", coverage_conditions={"all": [{"fact": "units", "op": ">=", "value": 50}]})
    assert "t-false" not in entries(bldg("CA", "Fresno, CA", units=10), rules=[rule])


@pytest.mark.parametrize("status,effective", [("pending", None), ("not_yet_effective", "2027-03-01")])
def test_false_coverage_is_omitted_before_temporal_status(status, effective):
    rule = dict(RULES[0], team_rule_id="t-future-outside", status=status, effective_date=effective,
                coverage_conditions={"all": [{"fact": "units", "op": ">=", "value": 50}]})
    assert "t-future-outside" not in entries(bldg("CA", "Fresno, CA", units=10), rules=[rule])


def test_unknown_coverage_keeps_future_rule_visible():
    rule = dict(RULES[0], team_rule_id="t-future-unknown", status="not_yet_effective",
                effective_date="2027-03-01",
                coverage_conditions={"all": [{"fact": "units", "op": ">=", "value": 50}]})
    assert entries(bldg("CA", "Fresno, CA", units=None), rules=[rule])["t-future-unknown"]["result"] == \
        "not_yet_effective"


def test_owner_type_unknown():
    rule = dict(RULES[0], team_rule_id="t-own",
                coverage_conditions={"all": [{"fact": "owner_type", "op": "==", "value": "corporate"}]})
    e = entries(bldg("CA", "Fresno, CA"), rules=[rule])["t-own"]
    assert e["result"] == "unknown" and "owner type" in e["explanation"]



def test_sf_1950_cap_superseded():
    es = entries(bldg("CA", "San Francisco, CA", year=1950))
    assert es["dev-sf-rent"]["result"] == "applies"
    assert es["dev-ca-cap"]["result"] == "superseded"


def test_sf_1979_cap_unknown():
    es = entries(bldg("CA", "San Francisco, CA", year=1979, threshold=True))
    assert es["dev-ca-cap"]["result"] == "unknown"


def test_pending_city_rule_never_supersedes():
    rules = copy.deepcopy(RULES)
    for r in rules:
        if r["team_rule_id"] == "dev-sf-rent":
            r["status"] = "pending"
    es = entries(bldg("CA", "San Francisco, CA", year=1950), rules=rules)
    assert es["dev-sf-rent"]["result"] == "pending"
    assert es["dev-ca-cap"]["result"] == "applies"


def test_no_generic_ca_rent_fallback():
    st, ct = rule("s", "CA", "state", "rent_increase_limits"), rule("c", "San Francisco, CA", "city", "rent_increase_limits")
    e = one(bldg("CA", "San Francisco, CA"), [st, ct], "s")
    assert e["result"] == "applies" and e["conflict_flag"] is False


def test_supersedes_direction_from_interaction():
    cov = {"summary": "x", "construction_date_basis": None, "built_on_or_before": None, "built_after": None,
           "min_building_age_years": None, "min_units": None, "max_units": None,
           "owner_conditions": None, "other_conditions": None}
    st = rule("s", "CA", "state", "rent_increase_limits", cov, overrides=["c"], interaction="Lists local rules.")
    ct = rule("c", "San Francisco, CA", "city", "rent_increase_limits", cov, overrides=["s"],
              interaction="Supersedes s (state cap).")
    b = bldg("CA", "San Francisco, CA")
    assert one(b, [st, ct], "s")["result"] == "superseded"
    assert one(b, [st, ct], "c")["result"] == "applies"



def test_generic_same_category_is_not_a_conflict():
    st, ct = rule("s", "MA", "state", "security_deposits"), rule("c", "Boston, MA", "city", "security_deposits")
    assert one(bldg("MA", "Boston, MA"), [st, ct], "s")["conflict_flag"] is False


def test_t3_pair_is_not_inferred_from_city_names():
    st = rule("nj", "NJ", "state", "algorithmic_rent_setting")
    ct = rule("jc", "Jersey City, NJ", "city", "algorithmic_rent_setting")
    b = bldg("NJ", "Jersey City, NJ")
    assert not one(b, [st, ct], "nj")["conflict_flag"]
    assert not one(b, [st, ct], "jc")["conflict_flag"]


def test_links_conflict():
    a, c = rule("a", "MA", "state", "security_deposits"), rule("b", "Boston, MA", "city", "security_deposits")
    links = {"supersedes": set(), "conflicts": {frozenset(("a", "b"))}, "uncertain": set()}
    assert all(e["conflict_flag"] for e in verdicts_for_building(bldg("MA", "Boston, MA"), [a, c], AS_OF, links))


def test_part1_conflict_type_sets_flag_and_explains_it():
    r = rule("c", "MA", "state", "security_deposits", conflict_type="source_date_disagreement")
    e = one(bldg("MA", "Boston, MA"), [r], "c")
    assert e["conflict_flag"] is True
    assert "Part 1 conflict classification: source_date_disagreement" in e["explanation"]
