import json

import pytest

from engine import precedence as P

AS_OF = "2026-10-01"


def rule(rid, jurisdiction, category, level=None, **kw):
    level = level or ("state" if len(jurisdiction) == 2 else "city")
    return {"team_rule_id": rid, "jurisdiction": jurisdiction, "level": level, "category": category,
            "status": kw.pop("status", "in_force"), "title": kw.pop("title", f"Rule {rid}"), "requirement": "x",
            "interaction": None, "coverage_conditions": kw.pop("coverage", None), "exemptions": None,
            "quoted_span": "q", "citation": kw.pop("citation", f"Code {rid}"), **kw}


def ann(**flags):
    return {**P.DEFAULT, **flags}


def v(result, *missing):
    out = {"result": result, "explanation": f"base {result}."}
    if missing:
        out["missing_facts"] = list(missing)
    return out


LA = {"address_id": "T1", "state": "CA", "legal_city": "Los Angeles, CA", "city_status": "resolved"}
JC = {"address_id": "T2", "state": "NJ", "legal_city": "Jersey City, NJ", "city_status": "resolved"}

STATE = rule("s1", "CA", "just_cause_eviction")
LOCAL = rule("l1", "Los Angeles, CA", "just_cause_eviction")
OTHER = rule("l2", "Los Angeles, CA", "just_cause_eviction")
A_YIELD = {"s1": ann(yields_to_local=True), "l1": ann(supersedes_state=True), "l2": ann()}



def test_b1_state_superseded_when_local_applies():
    res, log = P.apply_precedence({"s1": v("applies"), "l1": v("applies")}, [STATE, LOCAL], A_YIELD, LA, AS_OF)
    assert res["s1"]["result"] == "superseded" and res["s1"]["superseded_by"] == "l1"
    assert "l1" in res["s1"]["explanation"] and res["l1"]["result"] == "applies"
    assert log[0]["action"] == "superseded" and log[0]["by"] == "l1"


def test_b1_unknown_cascade_names_local_missing_fact():
    base = {"s1": v("applies"), "l1": v("unknown", "year built is missing")}
    res, _ = P.apply_precedence(base, [STATE, LOCAL], A_YIELD, LA, AS_OF)
    assert res["s1"]["result"] == "unknown"
    assert res["s1"]["missing_facts"] == ["year built is missing"]
    assert "Rule l1 (l1)" in res["s1"]["explanation"]
    assert base["s1"]["result"] == "applies"


def test_b1_needs_both_annotations_and_an_active_local():
    rules = [STATE, LOCAL, OTHER]
    res, _ = P.apply_precedence({"s1": v("applies"), "l1": None, "l2": v("applies")}, rules, A_YIELD, LA, AS_OF)
    assert res["s1"]["result"] == "applies" and res["l1"] is None
    res, _ = P.apply_precedence({"s1": v("applies"), "l1": v("applies")}, [STATE, LOCAL],
                                {"s1": ann(), "l1": ann(supersedes_state=True)}, LA, AS_OF)
    assert res["s1"]["result"] == "applies"
    res, _ = P.apply_precedence({"s1": v("applies"), "l1": v("not_yet_effective")}, [STATE, LOCAL], A_YIELD, LA, AS_OF)
    assert res["s1"]["result"] == "applies"


def test_b1_other_category_or_other_state_never_supersedes():
    cat = rule("l3", "Los Angeles, CA", "rent_increase_limits")
    far = rule("l4", "Newark, NJ", "just_cause_eviction")
    a = {"s1": ann(yields_to_local=True), "l3": ann(supersedes_state=True), "l4": ann(supersedes_state=True)}
    res, _ = P.apply_precedence({"s1": v("applies"), "l3": v("applies"), "l4": v("applies")},
                                [STATE, cat, far], a, LA, AS_OF)
    assert res["s1"]["result"] == "applies"



OLD = rule("lo", "Los Angeles, CA", "just_cause_eviction", coverage={"built_on_or_before": "1978-10-01"})
NEW = rule("ln", "Los Angeles, CA", "just_cause_eviction", coverage={"summary": "units not under the old ordinance"})
A_SPLIT = {"s1": ann(yields_to_local=True), "lo": ann(supersedes_state=True),
           "ln": ann(supersedes_state=True, construction_cutoff={"covered_if": "after", "date": "1978-10-01"})}


def test_b2_complementary_split_supersedes_even_if_each_unknown():
    base = {"s1": v("applies"), "lo": v("unknown", "year built"), "ln": v("unknown", "year built")}
    res, log = P.apply_precedence(base, [STATE, OLD, NEW], A_SPLIT, LA, AS_OF)
    assert res["s1"]["result"] == "superseded" and res["s1"]["superseded_by"] == "ln"
    assert "complementary" in res["s1"]["explanation"]
    assert log[0]["action"] == "superseded_complementary"


def test_b2_not_when_cutoffs_differ_or_place_unconfirmed():
    other = dict(A_SPLIT, ln=ann(supersedes_state=True, construction_cutoff={"covered_if": "after", "date": "1990-01-01"}))
    base = {"s1": v("applies"), "lo": v("unknown", "year built"), "ln": v("unknown", "year built")}
    assert P.apply_precedence(base, [STATE, OLD, NEW], other, LA, AS_OF)[0]["s1"]["result"] == "unknown"
    postal = dict(LA, city_status="postal_fallback")
    assert P.apply_precedence(base, [STATE, OLD, NEW], A_SPLIT, postal, AS_OF)[0]["s1"]["result"] == "unknown"


def test_b2_structured_built_after_counts():
    new = rule("ln", "Los Angeles, CA", "just_cause_eviction", coverage={"built_after": "1978-10-01"})
    a = dict(A_SPLIT, ln=ann(supersedes_state=True))
    assert P.complementary([OLD, new], a)
    assert not P.complementary([OLD], a)



FAIR = rule("nj", "NJ", "algorithmic_rent_setting", status="not_yet_effective", effective_date="2027-07-01")
JC_BAN = rule("jc", "Jersey City, NJ", "algorithmic_rent_setting")
A_PRE = {"nj": ann(may_preempt_local=True), "jc": ann()}


def test_b3_conflict_on_both_when_both_reach():
    res, log = P.apply_precedence({"nj": v("applies"), "jc": v("applies")}, [FAIR, JC_BAN], A_PRE, JC, AS_OF)
    assert res["nj"]["conflict_with"] == ["jc"] and res["jc"]["conflict_with"] == ["nj"]
    assert res["jc"]["result"] == "applies" and res["nj"]["result"] == "applies"
    assert [r["action"] for r in log] == ["conflict"]


def test_b3_no_conflict_before_the_state_law_takes_effect():
    res, log = P.apply_precedence({"nj": v("not_yet_effective"), "jc": v("applies")}, [FAIR, JC_BAN], A_PRE, JC, AS_OF)
    assert "conflict_with" not in res["jc"] and not log


def test_b3_no_conflict_when_local_omitted_or_state_pending():
    res, _ = P.apply_precedence({"nj": v("applies"), "jc": None}, [FAIR, JC_BAN], A_PRE, JC, AS_OF)
    assert "conflict_with" not in res["nj"]
    res, _ = P.apply_precedence({"nj": v("pending"), "jc": v("applies")}, [FAIR, JC_BAN], A_PRE, JC, AS_OF)
    assert "conflict_with" not in res["jc"]
    res, _ = P.apply_precedence({"nj": v("applies"), "jc": v("superseded")}, [FAIR, JC_BAN], A_PRE, JC, AS_OF)
    assert "conflict_with" not in res["jc"]


def test_b3_yields_to_local_cannot_preempt(corpus):
    good = {"doc_id": "DZ1", "quote": "shall be prohibited"}
    a, rejects = P.verify_annotation({"yields_to_local": True, "may_preempt_local": True,
                                      "evidence": {"yields_to_local": good, "may_preempt_local": good}}, types={})
    assert a["yields_to_local"] is True and a["may_preempt_local"] is False
    assert rejects == [{"field": "may_preempt_local", "reason": "yields_to_local and may_preempt_local are exclusive"}]
    res, log = P.apply_precedence({"nj": v("applies"), "jc": v("applies")}, [FAIR, JC_BAN],
                                  {"nj": ann(may_preempt_local=True, yields_to_local=True)}, JC, AS_OF)
    assert "conflict_with" not in res["jc"] and log[-1]["action"] == "may_preempt_ignored"



def test_b4_filter_edges():
    s2 = rule("s2", "CA", "just_cause_eviction", citation="Old version AB 9")
    s3 = rule("s3", "CA", "rent_increase_limits")
    ev = rule("le", "Los Angeles, CA", "just_cause_eviction")
    rules = [STATE, LOCAL, OTHER, s2, s3, ev, rule("sx", "CA", "just_cause_eviction")]
    a = {**A_YIELD, "le": ann(event_only=True),
         "sx": ann(supersedes_same_level=True, supersedes_same_level_citations=["AB 9"])}
    edges = {("l1", "l2"), ("l1", "s3"), ("s1", "s2"), ("s1", "l2"), ("l1", "s1"), ("l2", "s1"), ("sx", "s2"),
             ("le", "l1"), ("zz", "s1")}
    kept, rejected = P.filter_edges(rules, a, edges)
    assert kept == {("s1", "l2"), ("l1", "s1"), ("sx", "s2")}
    why = {(r["winner"], r["loser"]): r["reason"] for r in rejected}
    assert "same city" in why[("l1", "l2")]
    assert "different categories" in why[("l1", "s3")]
    assert "two state rules" in why[("s1", "s2")]
    assert "supersedes_state" in why[("l2", "s1")]
    assert "event" in why[("le", "l1")]
    assert "not in rules" in why[("zz", "s1")]


def test_b4_preemption_and_modifies_local_edges_rejected():
    mod = rule("m", "NJ", "rent_increase_limits")
    loc = rule("r", "Jersey City, NJ", "rent_increase_limits")
    a = {**A_PRE, "m": ann(modifies_local=True)}
    kept, rejected = P.filter_edges([FAIR, JC_BAN, mod, loc], a, {("nj", "jc"), ("m", "r")})
    assert kept == set() and len(rejected) == 2


def test_kept_edge_applied():
    s2 = rule("s2", "CA", "just_cause_eviction")
    res, _ = P.apply_precedence({"s1": v("applies"), "s2": v("applies")}, [STATE, s2], {}, LA, AS_OF,
                                edges={("s1", "s2")})
    assert res["s2"]["result"] == "superseded" and res["s2"]["superseded_by"] == "s1"



MOD = rule("m", "NJ", "rent_increase_limits", coverage={"min_building_age_years": 30})
RC = rule("rc", "Jersey City, NJ", "rent_increase_limits")
A_MOD = {"m": ann(modifies_local=True, modifies_local_missing_fact="certificate of occupancy within 30 years",
                  modifies_local_test={"fact": "certificate_of_occupancy_date", "op": ">", "value_years_before_as_of": 30})}


@pytest.mark.parametrize("year, expect", [(2010, None), (None, "unknown"), (1950, "applies")])
def test_b5_modifies_local(year, expect):
    b = dict(JC, year_built=year)
    base = {"m": v("applies") if year and year < 1996 else None, "rc": v("applies")}
    res, log = P.apply_precedence(base, [MOD, RC], A_MOD, b, AS_OF)
    assert res["m"] is None
    assert (res["rc"] or {}).get("result") == expect
    if expect == "unknown":
        assert res["rc"]["missing_facts"] == ["certificate of occupancy within 30 years"]
    if expect is None:
        assert any(r["action"] == "omitted_by_modifies_local" and r["by"] == "m" for r in log)


def test_b5_only_same_state_and_category():
    sf = rule("sf", "San Francisco, CA", "rent_increase_limits")
    other = rule("ab", "Jersey City, NJ", "algorithmic_rent_setting")
    b = dict(JC, year_built=2010)
    res, _ = P.apply_precedence({"m": None, "sf": v("applies"), "ab": v("applies")}, [MOD, sf, other], A_MOD, b, AS_OF)
    assert res["sf"]["result"] == "applies" and res["ab"]["result"] == "applies"


def test_cap_rule_guard():
    cap = rule("c", "MA", "rent_increase_limits")
    assert P.is_cap_rule(cap, ann()) and not P.is_cap_rule(cap, ann(bars_local_cap=True))
    cap["citation"] = "M.G.L. c. 40P, § 4"
    assert not P.is_cap_rule(cap, ann())
    assert not P.is_cap_rule(rule("d", "MA", "security_deposits"), ann())



@pytest.fixture
def corpus(tmp_path, monkeypatch):
    (tmp_path / "DZ1.txt").write_text("SOURCE: x\nA municipality shall be prohibited\nfrom enacting an ordinance.\n")
    monkeypatch.setattr(P, "TEXT_DIRS", [tmp_path])
    monkeypatch.setattr(P, "_TEXT_CACHE", {})
    return tmp_path


def test_verifier_rejects_non_verbatim_quote(corpus):
    path = corpus / "ann.json"
    good = {"doc_id": "DZ1", "quote": "a MUNICIPALITY shall be prohibited from enacting"}
    path.write_text(json.dumps({"annotations": {
        "k1": {"may_preempt_local": True, "evidence": {"may_preempt_local": good}},
        "k2": {"may_preempt_local": True, "evidence": {"may_preempt_local": {"doc_id": "DZ1", "quote": "shall preempt"}}},
        "k3": {"bars_local_cap": True, "evidence": {"bars_local_cap": [good, {"doc_id": "DZ9", "quote": "x"}]}}}}))
    v = P.verify_annotations(path)
    data = json.loads(path.read_text())["annotations"]
    assert data["k1"]["may_preempt_local"] is True
    assert data["k2"]["may_preempt_local"] is False and data["k3"]["bars_local_cap"] is False
    assert {(r["key"], r["field"]) for r in v["rejects"]} == {("k2", "may_preempt_local"), ("k3", "bars_local_cap")}


def test_hash_mismatch_gives_defaults(tmp_path):
    r = rule("s1", "CA", "just_cause_eviction")
    path = tmp_path / "ann.json"
    path.write_text(json.dumps({"annotations": {P.annotation_key(r): ann(yields_to_local=True)}}))
    got, missing = P.load_annotations([r], path=path)
    assert got["s1"]["yields_to_local"] is True and missing == []
    changed = dict(r, requirement="a new text from Part 1")
    got, missing = P.load_annotations([changed], path=path)
    assert got["s1"]["yields_to_local"] is False and missing == ["s1"]
    prepared = dict(r, interaction="rewritten by prepare_rules")
    got, missing = P.load_annotations([prepared], raw_rules=[r], path=path)
    assert got["s1"]["yields_to_local"] is True and missing == []
