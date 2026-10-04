from datetime import timedelta

from datetime import date


def to_date(s):
    if s is None:
        return None
    if isinstance(s, date):
        return s
    parts = str(s).split("-") + ["01", "01"]
    return date(int(parts[0]), int(parts[1]), int(parts[2]))

OMITTED = "omitted"


def _annotated(rule, annotations, key):
    if annotations and annotations.get(key) is not None:
        return annotations[key]
    return (rule.get("annotations") or {}).get(key)


def effective_on(rule):
    represented = to_date(rule.get("current_version_effective") or rule.get("figure_period_start")
                          or rule.get("effective_date"))
    if rule.get("law_in_force_since") or rule.get("in_force_since"):
        return represented
    dates = [d for d in (represented, to_date(rule.get("effective_date"))) if d is not None]
    return max(dates) if dates else None


def time_status(rule, annotations, as_of):
    annotations = annotations or {}
    as_of = to_date(as_of)
    status = rule.get("status")
    if status == "failed":
        return "failed", None
    enacted = to_date(annotations.get("enacted_on"))
    if enacted is not None and enacted > as_of:
        return "not_enacted", None
    if status == "pending":
        return "pending", None
    eff = effective_on(rule)
    since = to_date(rule.get("law_in_force_since") or rule.get("in_force_since") or
                    annotations.get("in_force_since"))
    current = to_date(rule.get("current_version_effective"))
    if current is not None and as_of < current:
        start = since or to_date(rule.get("effective_date"))
        if start is not None and as_of < start:
            return "not_yet_effective", None
        if start is None and rule.get("requirement_is_new") is True:
            return "not_yet_effective", None
        note = (f"Earlier version in force since {since.isoformat()}; " if since is not None else
                f"An earlier version applied on {as_of.isoformat()}; ")
        note += f"the current version takes effect on {current.isoformat()}."
        if rule.get("prior_version_note"):
            note += f" {rule['prior_version_note']}"
        return "in_force", note
    amends = bool(annotations.get("amends_existing_law") or
                  (rule.get("law_in_force_since") and rule.get("current_version_effective")))
    if amends and since is not None and eff is not None and since <= as_of < eff:
        return "in_force", (f"Earlier version in force since {since.isoformat()}; "
                            f"this amended version takes effect on {eff.isoformat()}.")
    if eff is not None:
        if eff > as_of:
            return "not_yet_effective", None
    elif status == "not_yet_effective":
        return "not_yet_effective", None
    sunset = to_date(rule.get("repeal_or_sunset_date") or rule.get("sunset_date"))
    if sunset is not None and as_of > sunset:
        return "expired", None
    figure_end = to_date(rule.get("figure_period_end"))
    if figure_end is not None and as_of > figure_end:
        return "in_force", (f"Figure for the period ending {figure_end.isoformat()}; "
                            "the next figure is not published in the corpus.")
    vu = to_date(rule.get("valid_until"))
    if vu is not None and as_of > vu:
        if rule.get("figure_period_end") or annotations.get("period_figure"):
            return "in_force", (f"Figure for the period ending {vu.isoformat()}; "
                                "the next figure is not published in the corpus.")
        return "expired", None
    return "in_force", None


def _age_thresholds(cov):
    out = []
    if isinstance(cov, dict):
        if cov.get("min_building_age_years") is not None:
            out.append(int(cov["min_building_age_years"]))
        for k in ("all", "any"):
            for p in cov.get(k) or []:
                out += _age_thresholds(p)
    return out


def _rule_date_boundaries(rule):
    annotations = rule.get("annotations") or {}
    for field in ("effective_date", "current_version_effective", "figure_period_start", "law_in_force_since",
                  "in_force_since", "enacted_on"):
        value = rule.get(field)
        if value is None:
            value = annotations.get(field)
        starts_on = to_date(value)
        if starts_on is not None:
            yield starts_on

    for field in ("repeal_or_sunset_date", "sunset_date", "figure_period_end", "valid_until"):
        ends_on = to_date(rule.get(field))
        if ends_on is not None:
            yield ends_on + timedelta(days=1)


def _building_age_boundaries(building, coverage):
    construction_year = building.get("year_built")
    if construction_year is None:
        return
    for minimum_age in _age_thresholds(coverage):
        threshold_year = int(construction_year) + minimum_age
        yield date(threshold_year, 1, 1)
        yield date(threshold_year, 12, 31)
        yield date(threshold_year + 1, 1, 1)


def collect_transition_dates(building, rules, start, end):
    start_date, end_date = to_date(start), to_date(end)
    transition_dates = set()
    for rule in rules:
        transition_dates.update(_rule_date_boundaries(rule))
        transition_dates.update(_building_age_boundaries(building, rule.get("coverage_conditions")))
    return sorted(transition_date for transition_date in transition_dates
                  if start_date <= transition_date <= end_date)


def _results_by_rule_id(entries):
    return {entry["team_rule_id"]: entry["result"] for entry in entries}


def _compare_rule_results(previous_results, current_results):
    changes = []
    for rule_id in sorted(previous_results.keys() | current_results.keys()):
        before = previous_results.get(rule_id, OMITTED)
        after = current_results.get(rule_id, OMITTED)
        if before != after:
            changes.append({"team_rule_id": rule_id, "before": before, "after": after})
    return changes


def build_rule_timeline(building, rules, start, end, evaluate=None):
    if evaluate is None:
        from .verdict import verdicts_for_building as evaluate
    start_date, end_date = to_date(start), to_date(end)
    previous_results = _results_by_rule_id(evaluate(building, rules, start_date.isoformat()))
    events = [{
        "date": start_date.isoformat(),
        "initial": True,
        "changes": [
            {"team_rule_id": rule_id, "before": OMITTED, "after": result}
            for rule_id, result in sorted(previous_results.items())
        ],
    }]

    for transition_date in collect_transition_dates(building, rules, start_date, end_date):
        if transition_date == start_date:
            continue
        current_results = _results_by_rule_id(evaluate(building, rules, transition_date.isoformat()))
        changes = _compare_rule_results(previous_results, current_results)
        if changes:
            events.append({"date": transition_date.isoformat(), "changes": changes})
        previous_results = current_results

    return events
