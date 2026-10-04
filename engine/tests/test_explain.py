import json
from pathlib import Path

from engine.adapt_coverage import evaluate as adapt_evaluate
from engine.explain import build_detail, concise_summary, coverage_checks, write
from engine.verdict import eval_coverage, to_date
from engine.voi import compute, missing_fact

AS_OF = "2026-10-01"
YEAR = "year_built / certificate_of_occupancy_date"
OFFICIAL = {"D1": "official", "D2": "secondary (law firm / news / mirror)"}


def b(**kw):
    d = {"address_id": "A1", "state": "CA", "legal_city": "Oakland, CA", "legal_city_candidate": None,
         "city_status": "resolved", "year_built": 1960, "units": 10, "units_min": 10, "units_max": 10,
         "units_method": "csv units field", "property_type": "multifamily_5plus", "threshold_year_case": False}
    d.update(kw)
    return d


def rule(rid, cov, jurisdiction="CA", level="state", confidence=0.9, doc="D1", **kw):
    r = {"team_rule_id": rid, "jurisdiction": jurisdiction, "level": level, "category": "x", "status": "in_force",
         "title": f"Rule {rid}", "coverage_conditions": cov, "effective_date": None, "source_doc_id": doc,
         "confidence": confidence, "overrides": [], "interaction": ""}
    r.update(kw)
    return r


def part1(**kw):
    d = {"summary": "s", "construction_date_basis": "year_built", "built_on_or_before": None, "built_after": None,
         "min_building_age_years": None, "min_units": None, "max_units": None, "owner_conditions": None,
         "other_conditions": None}
    d.update(kw)
    return d


def by_fact(checks):
    return {c["fact"]: c for c in checks}



def test_pre_cutoff_building():
    r = rule("r1", part1(built_on_or_before="1978-02-01"))
    (c,) = coverage_checks(b(year_built=1960), r, AS_OF)
    assert c == {"fact": "year_built", "building_value": 1960, "requirement": "built on or before 1978-02-01",
                 "outcome": "pass"}


def test_post_cutoff_building():
    r = rule("r1", part1(built_on_or_before="1978-02-01"))
    (c,) = coverage_checks(b(year_built=1995), r, AS_OF)
    assert c["outcome"] == "fail" and c["building_value"] == 1995
    r = rule("r2", part1(built_after="1978-02-01"))
    assert coverage_checks(b(year_built=1995), r, AS_OF)[0]["outcome"] == "pass"


def test_missing_year_and_cutoff_year():
    r = rule("r1", part1(built_on_or_before="1978-02-01"))
    (c,) = coverage_checks(b(year_built=None), r, AS_OF)
    assert c["outcome"] == "unknown" and c["building_value"] is None
    assert coverage_checks(b(year_built=1978), r, AS_OF)[0]["outcome"] == "unknown"
    roc = rule("r2", part1(construction_date_basis="certificate_of_occupancy", built_after="2000-01-01"))
    (c,) = coverage_checks(b(year_built=None), roc, AS_OF)
    assert c["fact"] == "certificate_of_occupancy_date" and c["outcome"] == "unknown"


def test_min_building_age_and_unit_checks():
    r = rule("r1", part1(min_building_age_years=15, min_units=5, max_units=20))
    c = by_fact(coverage_checks(b(year_built=2020), r, AS_OF))
    assert c["year_built"]["outcome"] == "fail"
    assert [k["outcome"] for k in coverage_checks(b(year_built=2000), r, AS_OF)] == ["pass", "pass", "pass"]
    assert coverage_checks(b(year_built=None), r, AS_OF)[0]["outcome"] == "unknown"


def test_unit_interval_unknown():
    r = rule("r1", part1(min_units=5))
    (c,) = coverage_checks(b(units=None, units_min=4, units_max=8), r, AS_OF)
    assert c["outcome"] == "unknown" and c["building_value"] == "4 to 8" and c["requirement"] == "at least 5 units"
    (c,) = coverage_checks(b(units=None, units_min=6, units_max=8), r, AS_OF)
    assert c["outcome"] == "pass"
    (c,) = coverage_checks(b(units=None, units_min=None, units_max=None), r, AS_OF)
    assert c["outcome"] == "unknown" and c["building_value"] is None


def test_dsl_checks_match_engine():
    cov = {"all": [{"fact": "units", "op": ">=", "value": 5},
                   {"any": [{"fact": "certificate_of_occupancy_date", "op": "<=", "value": "1978-02-01"},
                            {"fact": "owner_type", "op": "==", "value": "corporate"}]}]}
    r = rule("r1", cov)
    cs = coverage_checks(b(), r, AS_OF)
    assert [c["fact"] for c in cs] == ["units", "certificate_of_occupancy_date", "owner_type"]
    assert [c["outcome"] for c in cs] == ["pass", "pass", "unknown"]
    assert cs[2]["building_value"] is None and cs[1]["requirement"] == "<= 1978-02-01"
    assert coverage_checks(b(), rule("r2", "text only"), AS_OF)[0]["fact"] == "coverage_not_machine_readable"
    assert coverage_checks(b(), rule("r3", None), AS_OF) == []


def test_outcomes_equal_engine_three_valued_result():
    covs = [part1(built_on_or_before="1978-02-01", min_units=5), part1(built_after="2000-01-01"),
            part1(min_building_age_years=15, max_units=4),
            {"all": [{"fact": "units", "op": ">=", "value": 5}, {"fact": "year_built", "op": "<", "value": 1980}]},
            {"any": [{"fact": "units", "op": ">=", "value": 50}, {"fact": "year_built", "op": ">", "value": 2000}]}]
    blds = [b(year_built=1960), b(year_built=2010, units=2, units_min=2, units_max=2), b(year_built=None),
            b(year_built=1978, units=None, units_min=3, units_max=9)]
    for cov in covs:
        for bd in blds:
            checks = coverage_checks(bd, rule("r", cov), AS_OF)
            if "all" in cov or "any" in cov:
                engine = eval_coverage(bd, cov)[0]
            else:
                engine = adapt_evaluate(bd, cov, to_date(AS_OF))[0]
            outs = [c["outcome"] for c in checks]
            if "any" in cov:
                combined = "pass" if "pass" in outs else "unknown" if "unknown" in outs else "fail"
            else:
                combined = "fail" if "fail" in outs else "unknown" if "unknown" in outs else "pass"
            assert combined == {True: "pass", False: "fail", None: "unknown"}[engine], (cov, bd)



def lk(*results):
    return {"A1": [{"team_rule_id": rid, "result": res, "explanation": "x", "conflict_flag": False}
                   for rid, res in results]}


def detail(buildings, rules, lookups, details=None):
    return build_detail(lookups, buildings, rules, details or {}, AS_OF, source_types=OFFICIAL)


def test_detail_shape_and_fallback_missing_facts():
    r = rule("r1", part1(built_on_or_before="1978-02-01", min_units=5))
    out = detail({"A1": b(year_built=None, units=None, units_min=4, units_max=8)}, [r], lk(("r1", "unknown")))
    assert list(out) == ["as_of", "_meta", "addresses"] and out["as_of"] == AS_OF
    e = out["addresses"]["A1"]["rules"]["r1"]
    assert e["result"] == "unknown" and e["missing_facts"] == [YEAR, "units"]
    assert 15 <= len(e["summary"].split()) <= 25 and "r1" not in e["summary"]
    assert e["reasoning"] == "x"
    assert {c["outcome"] for c in e["checks"]} == {"unknown"}
    assert out["addresses"]["A1"]["excluded"] == []


def test_details_from_engine_take_precedence():
    r = rule("r1", part1(min_units=5))
    d = {"A1": {"r1": {"missing_facts": ["owner_type"], "checks": [], "omit_reason": None}}}
    e = detail({"A1": b()}, [r], lk(("r1", "applies")), d)["addresses"]["A1"]["rules"]["r1"]
    assert e["missing_facts"] == ["owner_type"] and e["checks"] == []


def test_unknown_without_checks_uses_explanation_and_place():
    r = rule("r1", {"summary": "s"})
    L = {"A1": [{"team_rule_id": "r1", "result": "unknown",
                 "explanation": "Rule: coverage depends on facts not in the data (small owner exemption not "
                                "verifiable from the data: x).", "conflict_flag": False}]}
    e = detail({"A1": b()}, [r], L)["addresses"]["A1"]["rules"]["r1"]
    assert e["missing_facts"] == ["condition: small owner exemption"]
    city = rule("r2", {}, jurisdiction="Oakland, CA", level="city")
    L = lk(("r2", "unknown"))
    e = detail({"A1": b(city_status="postal_fallback")}, [city], L)["addresses"]["A1"]["rules"]["r2"]
    assert e["missing_facts"][0] == "legal_city"


def test_confidence_multipliers():
    r = rule("r1", part1(min_units=5), confidence=0.9)
    plain = b()
    get = lambda bd, res="applies", rl=r: detail({"A1": bd}, [rl], lk((rl["team_rule_id"], res)))[
        "addresses"]["A1"]["rules"][rl["team_rule_id"]]
    assert get(plain)["confidence"] == 0.9
    assert get(plain, "unknown")["confidence"] == 0.45
    assert get(b(city_status="postal_fallback"))["confidence"] == 0.81
    inferred = b(units=None, units_min=6, units_max=8)
    assert get(inferred)["confidence"] == 0.81
    assert get(b(units_method="inferred from use code"))["confidence"] == 0.81
    nonunit = rule("r2", part1(built_on_or_before="1978-02-01"), confidence=0.9)
    assert get(inferred, rl=nonunit)["confidence"] == 0.9
    both = get(b(units=None, units_min=4, units_max=8, city_status="postal_only"), "unknown")
    assert both["confidence"] == round(0.9 * 0.5 * 0.9 * 0.9, 3) == 0.365
    missing = rule("r3", part1(), confidence=None)
    assert get(plain, rl=missing)["confidence"] == 0.8


def test_needs_review():
    low = rule("r1", part1(), confidence=0.7)
    assert detail({"A1": b()}, [low], lk(("r1", "applies")))["addresses"]["A1"]["rules"]["r1"]["needs_review"] is False
    assert detail({"A1": b()}, [low], lk(("r1", "unknown")))["addresses"]["A1"]["rules"]["r1"]["needs_review"] is True
    sec = rule("r2", part1(), confidence=0.95, doc="D2")
    e = detail({"A1": b()}, [sec], lk(("r2", "applies")))["addresses"]["A1"]["rules"]["r2"]
    assert e["confidence"] == 0.6 and e["needs_review"] is True
    unlisted = rule("r3", part1(), confidence=0.95, doc="D404")
    e = detail({"A1": b()}, [unlisted], lk(("r3", "applies")))["addresses"]["A1"]["rules"]["r3"]
    assert e["confidence"] == 0.6 and e["needs_review"]


def test_concise_summaries_are_measurable_and_never_leak_internal_ids():
    for result in ("applies", "unknown", "superseded", "pending", "not_yet_effective"):
        text = concise_summary(result, ["owner type / owner occupancy"], to_date(AS_OF))
        assert 15 <= len(text.split()) <= 25, (result, len(text.split()), text)
        assert "r-" not in text.lower()


def test_excluded_reasons():
    rules = [
        rule("in", part1()),
        rule("age", part1(min_units=20)),
        rule("failed", part1(), status="failed"),
        rule("old", part1(), valid_until="2026-06-30"),
        rule("future", part1(), status="not_yet_effective", effective_date="2027-01-01"),
        rule("given", part1(min_units=20)),
        rule("cond", part1()),
        rule("other_city", part1(), jurisdiction="Berkeley, CA", level="city"),
        rule("other_state", part1(), jurisdiction="NY"),
    ]
    d = {"A1": {"given": {"omit_reason": "engine says so"}}}
    out = detail({"A1": b()}, rules, lk(("in", "applies")), d)["addresses"]["A1"]
    ex = {e["team_rule_id"]: e["reason"] for e in out["excluded"]}
    assert list(ex) == ["age", "failed", "old", "future", "given", "cond"]
    assert ex["age"] == "coverage not met: units at least 20 units (building: 10)"
    assert ex["failed"] == "failed"
    assert ex["old"] == "end date passed (2026-06-30)"
    assert ex["future"] == "not in force on 2026-10-01 (effective 2027-01-01)"
    assert ex["given"] == "engine says so"
    assert "exemption" in ex["cond"]
    assert "in" in out["rules"]


def test_write_is_deterministic(tmp_path):
    r = rule("r1", part1(min_units=5))
    L = {"A2": [{"team_rule_id": "r1", "result": "applies", "explanation": "x"}],
         "A1": [{"team_rule_id": "r1", "result": "applies", "explanation": "x"}]}
    data = detail({"A1": b(), "A2": b()}, [r], L)
    p = tmp_path / "d.json"
    write(p, data)
    text = p.read_text()
    assert text.endswith("}\n") and json.loads(text) == data
    assert list(json.loads(text)["addresses"]) == ["A1", "A2"]
    write(p, detail({"A2": b(), "A1": b()}, [r], L))
    assert p.read_text() == text


def test_published_unknowns_never_use_generic_other_fact():
    published = json.loads((Path(__file__).parents[2] / "out" / "lookups_detail.json").read_text())
    unknowns = [d for row in published["addresses"].values() for d in row["rules"].values()
                if d["result"] == "unknown"]
    assert unknowns
    assert all(d["missing_facts"] and "other" not in d["missing_facts"] for d in unknowns)


def test_san_diego_unknowns_are_fully_accounted_for():
    root = Path(__file__).parents[2]
    buildings = json.loads((root / "out" / "buildings.json").read_text())
    published = json.loads((root / "out" / "lookups_detail.json").read_text())["addresses"]
    rows = [d for aid, row in published.items() if buildings[aid].get("legal_city") == "San Diego, CA"
            for d in row["rules"].values() if d["result"] == "unknown"]
    counts = {}
    for d in rows:
        for fact in d["missing_facts"]:
            counts[fact] = counts.get(fact, 0) + 1
    assert len(rows) == 152
    assert counts == {YEAR: 148, "legal_city": 4}



def _voi_inputs():
    blds = {"A1": {"legal_city": "Oakland, CA", "normalized_address": "1 A ST"},
            "A2": {"legal_city": "Berkeley, CA", "normalized_address": "2 B ST"}}
    u = "coverage depends on facts not in the data (unit count is missing)"
    L = {"A1": [{"team_rule_id": "r1", "result": "unknown", "explanation": u},
                {"team_rule_id": "r2", "result": "unknown", "explanation": u},
                {"team_rule_id": "r3", "result": "applies", "explanation": "ok"}],
         "A2": [{"team_rule_id": "r1", "result": "unknown", "explanation": u}]}
    return L, blds


def _rules_detail(**by_rule):
    return {"addresses": {aid: {"rules": {rid: {"missing_facts": f} for rid, f in rules.items()}, "excluded": []}
                          for aid, rules in by_rule.items()}}


def test_voi_uses_detail_missing_facts_once_per_fact():
    L, blds = _voi_inputs()
    d = _rules_detail(A1={"r1": ["units", YEAR], "r2": ["owner_type"], "r3": ["units"]},
                      A2={"r1": [YEAR, YEAR]})
    rows = {(r["missing_fact"], r["city"]): r for r in compute(L, blds, detail=d)}
    assert rows[("units", "Oakland, CA")] == {"missing_fact": "units", "city": "Oakland, CA", "unknown_answers": 1,
                                              "buildings": 1, "rules": ["r1"], "example_address": "1 A ST"}
    assert rows[(YEAR, "Oakland, CA")]["unknown_answers"] == 1
    assert rows[(YEAR, "Berkeley, CA")]["unknown_answers"] == 1
    assert rows[("owner_type", "Oakland, CA")]["rules"] == ["r2"]
    assert ("units", "Berkeley, CA") not in rows
    assert sum(r["unknown_answers"] for r in rows.values()) == 4


def test_voi_fallback_without_detail_or_for_unlisted_answers():
    L, blds = _voi_inputs()
    rows = compute(L, blds)
    assert len(rows) == 2 and rows[0]["missing_fact"] == "units" and rows[0]["unknown_answers"] == 2
    assert rows[0]["rules"] == ["r1", "r2"]
    partial = compute(L, blds, detail=_rules_detail(A1={"r1": ["owner_type"]}))
    got = {(r["missing_fact"], r["city"]): r["unknown_answers"] for r in partial}
    assert got == {("owner_type", "Oakland, CA"): 1, ("units", "Oakland, CA"): 1, ("units", "Berkeley, CA"): 1}
    empty = compute(L, blds, detail=_rules_detail(A1={"r1": [], "r2": []}, A2={"r1": []}))
    assert empty == rows
    assert missing_fact("unit count is missing") == "units"


def test_voi_compute_from_out_reads_detail_file(tmp_path):
    from engine.voi import compute_from_out
    L, blds = _voi_inputs()
    (tmp_path / "lookups.json").write_text(json.dumps({"as_of": AS_OF, "lookups": L}))
    (tmp_path / "buildings.json").write_text(json.dumps(blds))
    assert compute_from_out(tmp_path)[0]["missing_fact"] == "units"
    (tmp_path / "lookups_detail.json").write_text(json.dumps(_rules_detail(A1={"r1": ["owner_type"]})))
    assert {r["missing_fact"] for r in compute_from_out(tmp_path)} == {"owner_type", "units"}
