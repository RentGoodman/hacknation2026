import importlib
from datetime import date

from engine.temporal import collect_transition_dates, time_status, build_rule_timeline

AS_OF = date(2026, 10, 1)


def rule(rid="t-1", **kw):
    r = {"team_rule_id": rid, "title": f"Rule {rid}", "jurisdiction": "CA", "level": "state", "status": "in_force",
         "effective_date": "2020-01-01", "coverage_conditions": {}, "overrides": [], "category": "x"}
    r.update(kw)
    return r


def bldg(year=2000):
    return {"state": "CA", "legal_city": None, "city_status": "resolved", "year_built": year, "units": 10,
            "property_type": "multifamily_5plus", "threshold_year_case": False}


def test_failed_is_failed():
    assert time_status(rule(status="failed"), {}, AS_OF) == ("failed", None)


def test_pending_is_pending():
    assert time_status(rule(status="pending", effective_date=None), {}, AS_OF) == ("pending", None)


def test_not_enacted_uses_enacted_on():
    assert time_status(rule(), {"enacted_on": "2027-01-01"}, AS_OF) == ("not_enacted", None)
    assert time_status(rule(), {"enacted_on": "2019-06"}, AS_OF)[0] == "in_force"
    assert time_status(rule(), {}, AS_OF)[0] == "in_force"


def test_future_effect():
    r = rule(effective_date="2027-01-01")
    assert time_status(r, {}, AS_OF) == ("not_yet_effective", None)
    assert time_status(r, {}, "2027-01-01")[0] == "in_force"
    assert time_status(rule(effective_date="2027-03"), {}, AS_OF)[0] == "not_yet_effective"


def test_status_not_yet_effective_without_date():
    assert time_status(rule(effective_date=None, status="not_yet_effective"), {}, AS_OF)[0] == "not_yet_effective"


def test_valid_until_passed_without_period_figure_expires():
    r = rule(valid_until="2026-06-30")
    assert time_status(r, {}, AS_OF) == ("expired", None)
    assert time_status(r, {}, "2026-06-30")[0] == "in_force"


def test_valid_until_passed_with_period_figure_stays_in_force():
    r = rule(valid_until="2026-06-30")
    assert time_status(r, {"period_figure": True}, AS_OF) == (
        "in_force", "Figure for the period ending 2026-06-30; the next figure is not published in the corpus.")


def test_figure_period_end_never_expires_the_law():
    r = rule(figure_period_end="2026-06-30")
    status, note = time_status(r, {}, AS_OF)
    assert status == "in_force"
    assert "next figure" in note
    assert date(2026, 7, 1) in collect_transition_dates(bldg(), [r], "2026-01-01", "2027-01-01")


def test_amended_law_window():
    r = rule(effective_date="2027-01-01")
    ann = {"amends_existing_law": True, "in_force_since": "2019-01-01"}
    status, note = time_status(r, ann, AS_OF)
    assert status == "in_force"
    assert note == "Earlier version in force since 2019-01-01; this amended version takes effect on 2027-01-01."
    assert time_status(r, ann, "2018-12-31")[0] == "not_yet_effective"
    assert time_status(r, ann, "2027-01-01") == ("in_force", None)
    assert time_status(r, {"in_force_since": "2019-01-01"}, AS_OF)[0] == "not_yet_effective"


def test_part1_version_fields_override_legacy_dates():
    r = rule(effective_date="2030-01-01", law_in_force_since="2019-01-01",
             current_version_effective="2027-01-01")
    status, note = time_status(r, {}, AS_OF)
    assert status == "in_force"
    assert "Earlier version in force since 2019-01-01" in note
    assert time_status(r, {}, "2027-01-01") == ("in_force", None)


def test_prior_version_note_alone_does_not_put_a_rule_in_force_early():
    r = rule(effective_date="2024-07-01", current_version_effective="2026-01-01",
             requirement_is_new=False,
             prior_version_note="The source expressly describes the cap that applied before July 1, 2024.")
    assert time_status(r, {}, "2024-01-01") == ("not_yet_effective", None)

    figure = rule(effective_date="2026-03-01", current_version_effective="2026-03-01",
                  requirement_is_new=False,
                  prior_version_note="The source gives a 1.4% figure for 2025-03-01 through 2026-02-28.")
    assert time_status(figure, {}, "2026-02-15") == ("not_yet_effective", None)


def test_prior_version_in_force_from_proved_in_force_since():
    r = rule(effective_date="2026-03-01", current_version_effective="2026-03-01", requirement_is_new=False,
             prior_version_note="Earlier figure.")
    status, note = time_status(r, {"amends_existing_law": True, "in_force_since": "1979-06-13"}, "2026-02-15")
    assert status == "in_force"
    assert "1979-06-13" in note
    assert time_status(r, {"amends_existing_law": True, "in_force_since": "1979-06-13"}, "1979-01-01") == \
        ("not_yet_effective", None)


def test_prior_version_requires_source_backed_note():
    r = rule(effective_date="2024-07-01", current_version_effective="2026-01-01",
             requirement_is_new=False, prior_version_note=None)
    assert time_status(r, {}, "2024-01-01") == ("not_yet_effective", None)


def test_conflicting_published_dates_later_effective_date_wins():
    from engine.temporal import effective_on
    r = rule(effective_date="2026-03-01", current_version_effective="2026-01", requirement_is_new=False)
    assert effective_on(r) == date(2026, 3, 1)
    assert time_status(r, {}, "2025-12-31") == ("not_yet_effective", None)
    assert time_status(r, {}, "2026-01-02") == ("not_yet_effective", None)
    assert time_status(r, {}, "2026-03-01") == ("in_force", None)


def test_part1_figure_period_and_sunset_fields():
    figure = rule(effective_date=None, figure_period_start="2026-01-01", figure_period_end="2026-06-30")
    assert time_status(figure, {}, AS_OF) == (
        "in_force", "Figure for the period ending 2026-06-30; the next figure is not published in the corpus.")
    sunset = rule(effective_date=None, repeal_or_sunset_date="2026-06-30")
    assert time_status(sunset, {}, AS_OF) == ("expired", None)


def test_collect_transition_dates_include_part1_contract_dates():
    r = rule(effective_date=None, current_version_effective="2027-01-01", repeal_or_sunset_date="2027-06-30")
    assert collect_transition_dates(bldg(), [r], "2026-01-01", "2028-01-01") == [date(2027, 1, 1), date(2027, 7, 1)]


def fake_eval(building, rules, as_of):
    from engine.verdict import to_date
    d = to_date(as_of)
    out = []
    for r in rules:
        eff, vu = to_date(r.get("effective_date")), to_date(r.get("valid_until"))
        if eff and d < eff:
            res = "not_yet_effective"
        elif vu and d > vu:
            continue
        else:
            n = (r.get("coverage_conditions") or {}).get("min_building_age_years")
            if n is not None and d.year - building["year_built"] < n:
                continue
            res = "applies"
        out.append({"team_rule_id": r["team_rule_id"], "result": res})
    return out


def test_timeline_only_change_dates():
    rules = [rule("a", effective_date="2025-01-01", valid_until="2025-12-31"),
             rule("b", effective_date="2024-06-01"),
             rule("c", effective_date="2019-01-01")]
    tl = build_rule_timeline(bldg(), rules, "2024-01-01", "2028-12-31", evaluate=fake_eval)
    assert [t["date"] for t in tl] == ["2024-01-01", "2024-06-01", "2025-01-01", "2026-01-01"]
    assert tl[0]["initial"] is True
    assert tl[0]["changes"] == [{"team_rule_id": "a", "before": "omitted", "after": "not_yet_effective"},
                                {"team_rule_id": "b", "before": "omitted", "after": "not_yet_effective"},
                                {"team_rule_id": "c", "before": "omitted", "after": "applies"}]
    assert tl[1]["changes"] == [{"team_rule_id": "b", "before": "not_yet_effective", "after": "applies"}]
    assert tl[2]["changes"] == [{"team_rule_id": "a", "before": "not_yet_effective", "after": "applies"}]
    assert tl[3]["changes"] == [{"team_rule_id": "a", "before": "applies", "after": "omitted"}]


def test_timeline_skips_collect_transition_dates_without_change():
    rules = [rule("a"), rule("b", annotations={"in_force_since": "2025-01-01"}), rule("c", valid_until="2035-01-01")]
    assert date(2025, 1, 1) in collect_transition_dates(bldg(), rules, "2024-01-01", "2028-12-31")
    tl = build_rule_timeline(bldg(), rules, "2024-01-01", "2028-12-31", evaluate=fake_eval)
    assert [t["date"] for t in tl] == ["2024-01-01"]


def test_timeline_finds_rolling_15_year_boundary():
    rules = [rule("old", coverage_conditions={"min_building_age_years": 15})]
    b = bldg(year=2011)
    assert date(2026, 1, 1) in collect_transition_dates(b, rules, "2024-01-01", "2028-12-31")
    assert date(2026, 12, 31) in collect_transition_dates(b, rules, "2024-01-01", "2028-12-31")
    tl = build_rule_timeline(b, rules, "2024-01-01", "2028-12-31", evaluate=fake_eval)
    assert [t["date"] for t in tl] == ["2024-01-01", "2026-01-01"]
    assert tl[0]["changes"] == []
    assert tl[1]["changes"] == [{"team_rule_id": "old", "before": "omitted", "after": "applies"}]


def test_rolling_bound_found_in_nested_dsl_and_without_year_built():
    nested = rule("n", effective_date=None, coverage_conditions={"all": [{"fact": "units", "op": ">=", "value": 2},
                                                   {"any": [{"min_building_age_years": 10}]}]})
    assert date(2020, 1, 1) in collect_transition_dates(bldg(2010), [nested], "2019-01-01", "2021-01-01")
    assert collect_transition_dates({"year_built": None}, [nested], "2019-01-01", "2030-01-01") == []


def test_valid_until_plus_one_day_is_a_candidate():
    r = rule(valid_until="2025-06-30", effective_date=None)
    assert collect_transition_dates(bldg(), [r], "2024-01-01", "2028-12-31") == [date(2025, 7, 1)]


def test_timeline_is_deterministic():
    rules = [rule("b", effective_date="2025-01-01"), rule("a", effective_date="2025-01-01")]
    a = build_rule_timeline(bldg(), rules, "2024-01-01", "2028-12-31", evaluate=fake_eval)
    b = build_rule_timeline(bldg(), list(reversed(rules)), "2024-01-01", "2028-12-31", evaluate=fake_eval)
    assert a == b


def test_cli_importable():
    mod = importlib.import_module("engine.timeline")
    assert callable(mod.main)
    assert mod.main(["--address", "A0001", "--start", "2025-01-01", "--end", "2024-01-01"]) == 2
    assert mod.main(["--address", "A0001", "--start", "nope"]) == 2
