from engine.contract_fields import apply_contract_fields, resolve_annotation


def test_part1_fields_win_and_disagreements_are_logged():
    rule = {"team_rule_id": "r1", "yields_to_local": True, "preempts_local": False,
            "law_in_force_since": "2020-01-01"}
    resolved, rows = resolve_annotation(rule, {"yields_to_local": False, "may_preempt_local": True,
                                               "in_force_since": "2019-01-01"})
    assert resolved["yields_to_local"] is True
    assert resolved["may_preempt_local"] is False
    assert resolved["in_force_since"] == "2020-01-01"
    assert {r["part1_field"] for r in rows} == {"yields_to_local", "preempts_local", "law_in_force_since"}
    assert all(r["resolution"] == "part1_field" for r in rows)


def test_figure_period_marks_period_figure_and_order_is_stable():
    rules = [{"team_rule_id": "b", "figure_period_end": "2026-12-31"}, {"team_rule_id": "a"}]
    resolved, rows = apply_contract_fields(rules, {"a": {}, "b": {"period_figure": False}})
    assert resolved["b"]["period_figure"] is True
    assert rows == [{"team_rule_id": "b", "part1_field": "figure_period_start/figure_period_end",
                     "part1_value": [None, "2026-12-31"], "annotation_field": "period_figure",
                     "annotation_value": False, "resolution": "part1_field"}]
