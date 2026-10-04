FIELD_TO_ANNOTATION = {
    "law_in_force_since": "in_force_since",
    "in_force_since": "in_force_since",
    "yields_to_local": "yields_to_local",
    "preempts_local": "may_preempt_local",
}


def resolve_annotation(rule, annotation):
    resolved = dict(annotation or {})
    disagreements = []
    for field, key in FIELD_TO_ANNOTATION.items():
        if rule.get(field) is None:
            continue
        value = rule[field]
        old = resolved.get(key)
        if old is not None and old != value:
            disagreements.append({
                "team_rule_id": rule["team_rule_id"],
                "part1_field": field,
                "part1_value": value,
                "annotation_field": key,
                "annotation_value": old,
                "resolution": "part1_field",
            })
        resolved[key] = value

    if rule.get("figure_period_start") is not None or rule.get("figure_period_end") is not None:
        old = resolved.get("period_figure")
        if old is not True:
            disagreements.append({
                "team_rule_id": rule["team_rule_id"],
                "part1_field": "figure_period_start/figure_period_end",
                "part1_value": [rule.get("figure_period_start"), rule.get("figure_period_end")],
                "annotation_field": "period_figure",
                "annotation_value": old,
                "resolution": "part1_field",
            })
        resolved["period_figure"] = True
    return resolved, disagreements


def apply_contract_fields(rules, annotations):
    out, disagreements = {}, []
    for rule in sorted(rules, key=lambda r: r["team_rule_id"]):
        rid = rule["team_rule_id"]
        out[rid], rows = resolve_annotation(rule, annotations.get(rid) or {})
        disagreements.extend(rows)
    return out, disagreements
