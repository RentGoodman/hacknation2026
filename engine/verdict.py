from datetime import date

from buildings.api import matches_jurisdiction_record

from .adapt_coverage import evaluate as adapt_evaluate, is_part1
from .exemptions import evaluate_conditions
from .temporal import effective_on, time_status
from . import coverage_v3
from .audit_overrides import current_audit
from .links import current_links

DEFAULT_AS_OF = "2026-10-01"
ALWAYS_UNKNOWN_FACTS = {"owner_type", "tenancy_start"}
ACTIVE = {"applies", "unknown"}


def to_date(s):
    if s is None:
        return None
    if isinstance(s, date):
        return s
    parts = str(s).split("-") + ["01", "01"]
    return date(int(parts[0]), int(parts[1]), int(parts[2]))



def _cmp(a, op, b):
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b}[op]


def _units_range_text(lo, hi):
    if lo is not None and hi is not None:
        return f"public record gives {lo} to {hi} units"
    if lo is not None:
        return f"public record gives at least {lo} units"
    return f"public record gives at most {hi} units"


def _units(b, op, v):
    if b.get("units") is not None:
        if op == "in":
            return b["units"] in v, None
        return _cmp(b["units"], op, v), None
    lo, hi = b.get("units_min"), b.get("units_max")
    if lo is None and hi is None:
        return None, "unit count is missing"
    if lo is not None and hi is not None and lo == hi:
        return (lo in v, None) if op == "in" else (_cmp(lo, op, v), None)
    why = f"unit count unknown ({_units_range_text(lo, hi)})"
    if op == "in":
        if lo is not None and hi is not None and hi - lo <= 10000:
            hits = {n in v for n in range(lo, hi + 1)}
            if hits == {True}:
                return True, None
            if hits == {False}:
                return False, None
        return None, why
    all_ok = {">=": lo is not None and lo >= v, ">": lo is not None and lo > v,
              "<=": hi is not None and hi <= v, "<": hi is not None and hi < v,
              "==": False}[op]
    none_ok = {">=": hi is not None and hi < v, ">": hi is not None and hi <= v,
               "<=": lo is not None and lo > v, "<": lo is not None and lo >= v,
               "==": (lo is not None and lo > v) or (hi is not None and hi < v)}[op]
    if all_ok:
        return True, None
    if none_ok:
        return False, None
    return None, why


def _interval_compare(lower, upper, op, value):
    if op == "in":
        values = list(value)
        if lower is not None and lower == upper:
            return lower in values
        if not any((lower is None or item >= lower) and (upper is None or item <= upper) for item in values):
            return False
        return None
    if op == "==":
        if lower is not None and lower == upper:
            return lower == value
        if (lower is not None and value < lower) or (upper is not None and value > upper):
            return False
        return None
    if op in ("<", "<="):
        compare = (lambda item: item < value) if op == "<" else (lambda item: item <= value)
        if upper is not None and compare(upper):
            return True
        if lower is not None and not compare(lower):
            return False
        return None
    if op in (">", ">="):
        compare = (lambda item: item > value) if op == ">" else (lambda item: item >= value)
        if lower is not None and compare(lower):
            return True
        if upper is not None and not compare(upper):
            return False
        return None
    return None


def _co_interval(b):
    lo, hi = to_date(b.get("co_date_min")), to_date(b.get("co_date_max"))
    y = b.get("year_built")
    if y is not None:
        lo, hi = lo or date(y, 1, 1), hi or date(y, 12, 31)
    return (lo, hi) if lo is not None or hi is not None else None


def _co_date(b, op, v):
    cutoff = [to_date(item) for item in v] if op == "in" else to_date(v)
    iv = _co_interval(b)
    if iv is None:
        return None, "certificate of occupancy date and year built are both missing"
    lo, hi = iv
    result = _interval_compare(lo, hi, op, cutoff)
    if result is not None:
        return result, None
    shown_lo, shown_hi = lo.isoformat() if lo else "unknown", hi.isoformat() if hi else "unknown"
    shown_cutoff = ", ".join(item.isoformat() for item in cutoff) if op == "in" else cutoff.isoformat()
    return None, (f"certificate of occupancy date unknown (between {shown_lo} and {shown_hi}), "
                  f"cutoff {shown_cutoff}")


def _year_built(b, op, value):
    year = b.get("year_built")
    lower, upper = (year, year) if year is not None else (None, b.get("year_built_max"))
    if lower is None and upper is None:
        return None, "year built is missing"
    target = [int(x) if isinstance(x, str) and x.isdigit() else x for x in value] if op == "in" else \
        (int(value) if isinstance(value, str) and value.isdigit() else value)
    result = _interval_compare(lower, upper, op, target)
    return (result, None) if result is not None else \
        (None, f"year built unknown (public record gives an upper bound of {upper})")


def _year_built_date(b, op, value):
    cutoff = to_date(value)
    year = b.get("year_built")
    if year is not None:
        lower, upper = date(year, 1, 1), date(year, 12, 31)
    elif b.get("year_built_max") is not None:
        lower, upper = None, date(b["year_built_max"], 12, 31)
    else:
        return None, "year built is missing"
    result = _interval_compare(lower, upper, op, cutoff)
    if result is not None:
        return result, None
    shown_lo, shown_hi = lower.isoformat() if lower else "unknown", upper.isoformat() if upper else "unknown"
    return None, f"construction date unknown (between {shown_lo} and {shown_hi}), cutoff {cutoff.isoformat()}"


def eval_predicate(b, p):
    fact, op, v = p.get("fact"), p.get("op"), p.get("value")
    if fact in ALWAYS_UNKNOWN_FACTS:
        return None, f"{fact.replace('_', ' ')} is not in the data"
    if fact == "certificate_of_occupancy_date":
        return _co_date(b, op, v)
    if fact == "units":
        return _units(b, op, v)
    if fact == "year_built":
        return _year_built(b, op, v)
    val = b.get(fact)
    if val is None:
        return None, f"{fact.replace('_', ' ')} is missing"
    if op == "in":
        return val in v, None
    try:
        return _cmp(val, op, v), None
    except (TypeError, KeyError):
        return None, f"predicate on {fact} could not be evaluated"


def eval_coverage(b, cov):
    if cov is None or cov == {}:
        return True, None
    if isinstance(cov, str):
        return (True, None) if not cov.strip() else (None, "coverage not machine readable: " + cov.strip())
    if not isinstance(cov, dict) or not ({"all", "any"} & set(cov)):
        return None, "coverage not machine readable"
    mode = "all" if "all" in cov else "any"
    results = []
    for p in cov[mode]:
        results.append(eval_coverage(b, p) if ({"all", "any"} & set(p)) else eval_predicate(b, p))
    vals = [r for r, _ in results]
    unknown_reasons = [why for r, why in results if r is None and why]
    if mode == "all":
        if False in vals:
            return False, None
        return (True, None) if all(v is True for v in vals) else (None, "; ".join(unknown_reasons))
    if True in vals:
        return True, None
    return (False, None) if all(v is False for v in vals) else (None, "; ".join(unknown_reasons))



def eval_place(b, rule):
    limited_to = rule.get("applies_only_in")
    jurisdiction = limited_to or rule["jurisdiction"]
    level = "city" if limited_to else rule["level"]
    m = matches_jurisdiction_record(b, jurisdiction, level)
    if m == "yes" and level == "city" and b.get("city_status") == "postal_fallback":
        return "unknown"
    return m


def _place_unknown_note(b, rule):
    if b.get("city_status") == "postal_fallback":
        return (f" Legal city not confirmed: {b.get('legal_city')} comes from the postal city only "
                "(no geocoded point, no house number), so this city rule may or may not apply.")
    if b.get("city_status") == "postal_only" and b.get("legal_city_candidate"):
        return (f" Legal city not confirmed: postal city is {b['legal_city_candidate']} "
                "but the address could not be placed inside an incorporated city.")
    return (f" Legal city could not be determined (city_status {b.get('city_status')}), "
            f"so this {rule['jurisdiction']} rule may or may not apply.")


def eval_time(rule, as_of):
    status = rule.get("status")
    if status in ("failed", "pending"):
        return status
    eff = to_date(rule.get("effective_date"))
    if eff is not None:
        return "not_yet_effective" if eff > as_of else "in_force"
    return "not_yet_effective" if status == "not_yet_effective" else "in_force"


def base_verdict(b, rule, as_of):
    v, notes, omit = _base_verdict(b, rule, as_of)
    if v is not None and notes:
        v["explanation"] += " " + " ".join(notes)
    if v is None and omit:
        return {"result": None, "omit_reason": omit}
    return v


COVERAGE_FACTS = (("certificate of occupancy", "year_built / certificate_of_occupancy_date"),
                  ("year built", "year_built / certificate_of_occupancy_date"),
                  ("building age", "year_built / certificate_of_occupancy_date"),
                  ("construction date", "year_built / certificate_of_occupancy_date"),
                  ("unit count", "units"), ("owner type", "owner_type"),
                  ("owner occupancy", "owner type / owner occupancy"),
                  ("owner filed", "owner exemption filing"), ("tenancy start", "tenancy_start"),
                  ("not machine readable", "coverage_not_machine_readable"))


def _coverage_facts(why):
    w = (why or "").lower()
    if "missing facts:" in w:
        named = w.split("missing facts:", 1)[1]
        return [f.strip(" .") for f in named.split(";") if f.strip(" .")]
    return list(dict.fromkeys(f for k, f in COVERAGE_FACTS if k in w)) or (["other"] if w else [])


def _base_verdict(b, rule, as_of):
    place = eval_place(b, rule)
    time, time_note = time_status(rule, rule.get("_annotation"), as_of)
    raw_cov = rule.get("coverage_conditions")
    notes, facts = [], []
    if coverage_v3.has_v3_coverage(rule):
        cov, cov_why, notes = coverage_v3.evaluate(b, rule, as_of)
    elif is_part1(raw_cov):
        cov, cov_why, notes = adapt_evaluate(b, raw_cov, as_of)
    else:
        cov, cov_why = eval_coverage(b, raw_cov)
    if cov is None:
        facts = _coverage_facts(cov_why)
    bars_local_cap = (rule.get("_annotation") or {}).get("bars_local_cap")
    if rule.get("_conditions") is not None and bars_local_cap:
        notes = notes + [f"Limit on any permitted local regulation: {c['text'].strip()}" for c in rule["_conditions"]]
    elif rule.get("_conditions") is not None:
        coverage_notes = notes
        cov, cov_why, condition_notes, cond_facts = evaluate_conditions(b, rule["_conditions"], cov, cov_why)
        notes = coverage_notes + condition_notes
        facts = list(dict.fromkeys(facts + cond_facts)) if cov is None else []
    if time_note:
        notes = [time_note] + notes
    city_note = _place_unknown_note(b, rule) if place == "unknown" else ""
    if place == "no":
        return None, notes, None
    if time in ("failed", "not_enacted", "expired"):
        ended = rule.get("repeal_or_sunset_date") or rule.get("sunset_date") or rule.get("figure_period_end") \
            or rule.get("valid_until")
        return None, notes, {"failed": "failed (struck or rejected)", "not_enacted": f"not enacted on {as_of}",
                             "expired": f"end date {ended} passed"}[time]
    if cov is False:
        return None, notes, f"coverage conditions not met{(': ' + cov_why) if cov_why else ''}"
    if time == "pending":
        return {"result": "pending", "explanation": f"{rule['title']} is a pending bill or proposal, not law, as of {as_of}.{city_note}"}, notes, None
    if time == "not_yet_effective":
        eff = effective_on(rule)
        return {"result": "not_yet_effective", "explanation":
                f"{rule['title']} is enacted but takes effect on {eff.isoformat() if eff else 'a later date'}, "
                f"after {as_of}.{city_note}"}, notes, None
    if place == "unknown":
        return {"result": "unknown", "explanation": f"{rule['title']} applies in {rule['jurisdiction']}.{city_note}",
                "missing_facts": ["legal_city"]}, notes, None
    if cov is None:
        return {"result": "unknown", "explanation": f"{rule['title']}: coverage depends on facts not in the data ({cov_why}).",
                "missing_facts": facts}, notes, None
    scope = "Statewide rule" if rule["level"] == "state" else f"City rule for {rule['jurisdiction']}"
    return {"result": "applies", "explanation": f"{scope}, in force on {as_of}; the building meets its coverage conditions."}, notes, None


def _intrinsic_conflict(rule):
    return bool(rule.get("conflict_flag"))


RELATIONAL_CONFLICT_TYPES = {"preemption"}


def _other_level_reaches(rid, res, by_id):
    from .precedence import REACHES_LOCAL, REACHES_STATE, is_local_of
    rule, own = by_id[rid], res.get(rid)
    reaches = REACHES_STATE if rule.get("level") == "state" else REACHES_LOCAL
    if own is None or own["result"] not in reaches:
        return False
    for oid, other in res.items():
        o = by_id.get(oid)
        if oid == rid or other is None or o is None or o.get("category") != rule.get("category"):
            continue
        if rule.get("level") == "state" and is_local_of(o, rule.get("jurisdiction")) \
                and other["result"] in REACHES_LOCAL:
            return True
        if o.get("level") == "state" and is_local_of(rule, o.get("jurisdiction")) \
                and other["result"] in REACHES_STATE:
            return True
    return False


def _contract_conflict(rid, res, by_id):
    conflict_type = by_id[rid].get("conflict_type")
    if conflict_type in RELATIONAL_CONFLICT_TYPES and not _other_level_reaches(rid, res, by_id):
        return None
    return conflict_type


_GRAPH_CACHE = {}
UNCERTAIN_REASONS = {}


def override_graph(rules):
    audited = current_audit()
    key = (tuple((r["team_rule_id"], tuple(r.get("overrides") or []), r.get("interaction")) for r in rules),
           id(audited), len(audited))
    if key in _GRAPH_CACHE:
        return _GRAPH_CACHE[key]
    by = {r["team_rule_id"]: r for r in rules}
    sup, undirected = set(), set()
    for r in rules:
        a, text = r["team_rule_id"], r.get("interaction") or ""
        for o in r.get("overrides") or []:
            if o not in by:
                continue
            other = by[o].get("interaction") or ""
            if f"Supersedes {o}" in text or f"Yields to {a}" in other:
                sup.add((a, o))
            elif f"Yields to {o}" in text or f"Supersedes {a}" in other:
                sup.add((o, a))
            elif "Supersedes" not in text and "Yields to" not in text and is_dsl_rule(r):
                sup.add((a, o))
            else:
                undirected.add(frozenset((a, o)))
    undirected -= {frozenset(p) for p in sup}
    for pair, e in audited.items():
        sup = {p for p in sup if frozenset(p) != pair}
        undirected.discard(pair)
        if e["decision"] == "REAL_SUPERSESSION":
            loser = next(iter(pair - {e["winner"]}))
            sup.add((e["winner"], loser))
        elif e["decision"] == "UNCERTAIN":
            undirected.add(pair)
            UNCERTAIN_REASONS[pair] = e.get("reason") or ""
    _GRAPH_CACHE[key] = (sup, undirected)
    return _GRAPH_CACHE[key]


def is_dsl_rule(r):
    c = r.get("coverage_conditions")
    return not is_part1(c)


def _overrides(a, b, links, graph):
    return (a["team_rule_id"], b["team_rule_id"]) in graph[0] or \
        (a["team_rule_id"], b["team_rule_id"]) in links.get("supersedes", set())


def _referenced_rule(rule, ref, rules):
    import re
    ref_l = (ref or "").lower().strip()
    if not ref_l:
        return None
    acr = ref.strip() if ref.strip().isupper() and len(ref.strip()) <= 6 else None
    cands = []
    for r in rules:
        if r["team_rule_id"] == rule["team_rule_id"] or r["jurisdiction"] != rule["jurisdiction"]:
            continue
        text = f"{r.get('title') or ''} {r.get('citation') or ''}"
        if ref_l in text.lower() or (acr and re.search(rf"\b{re.escape(acr)}\b", text)):
            c = r.get("coverage_conditions") if isinstance(r.get("coverage_conditions"), dict) else {}
            decisive = any(c.get(k) is not None for k in ("built_on_or_before", "built_after",
                                                          "min_building_age_years", "min_units", "max_units"))
            cands.append((not decisive, r["team_rule_id"], r))
    return sorted(cands, key=lambda t: t[:2])[0][2] if cands else None


def _coverage_of(b, rule, as_of):
    raw = rule.get("coverage_conditions")
    if is_part1(raw):
        v, why, _ = adapt_evaluate(b, raw, as_of)
        return v, why
    return eval_coverage(b, raw)


def _compound_references(rule, ref, rules):
    import re
    parts = [p for p in re.split(r"\s+(?:and|or)\s+|\s*/\s*|\s*,\s*", (ref or "").strip()) if p]
    if len(parts) < 2:
        return None
    found = [_referenced_rule(rule, p, rules) for p in parts]
    return None if any(f is None for f in found) else found


def _resolve_references(b, rules, as_of):
    for r in rules:
        for c in r.get("_conditions") or []:
            if c.get("situation") != "references_coverage":
                continue
            ref = _referenced_rule(r, c.get("references"), rules)
            if ref is None:
                parts = _compound_references(r, c.get("references"), rules)
                if parts:
                    res = [(_coverage_of(b, p, as_of), p["team_rule_id"]) for p in parts]
                    vals = [v for (v, _), _ in res]
                    v = True if True in vals else (False if all(x is False for x in vals) else None)
                    why = "; ".join(w for (x, w), _ in res if x is None and w) or None
                    c["_ref_result"] = (v, why, "+".join(i for _, i in res))
                    continue
                c["_ref_result"] = (None, "referenced rule not found", None)
                own = r.get("coverage_conditions")
                if is_part1(own) and any(own.get(k) is not None for k in ("built_on_or_before", "built_after",
                                                                           "min_building_age_years")):
                    v, why, _ = adapt_evaluate(b, own, as_of)
                    c["_self_regime"] = (v, why)
                continue
            v, why = _coverage_of(b, ref, as_of)
            c["_ref_result"] = (v, why, ref["team_rule_id"])


_PREC_CACHE = {}


def precedence_context(rules, links):
    from .precedence import DEFAULT, collect_edges, filter_edges, filter_pairs
    audited = current_audit()
    key = (tuple((r["team_rule_id"], tuple(r.get("overrides") or []), r.get("interaction"), id(r.get("_annotation")))
                 for r in rules), id(audited), len(audited), links.get("source"), len(links.get("supersedes", ())))
    if key in _PREC_CACHE:
        return _PREC_CACHE[key]
    anns = {r["team_rule_id"]: r.get("_annotation") or DEFAULT for r in rules}
    graph = override_graph(rules)
    by = {r["team_rule_id"]: r for r in rules}
    for w, l in sorted(graph[0]):
        if w not in by or l not in by:
            continue
        W, L = by[w], by[l]
        if W.get("_annotation") is None and L.get("_annotation") is None and W["category"] == L["category"] \
                and W["level"] == "city" and L["level"] == "state" and W["jurisdiction"].endswith(", " + L["jurisdiction"]):
            anns[w] = {**anns[w], "supersedes_state": True, "source": "fallback: overrides + interaction"}
            anns[l] = {**anns[l], "yields_to_local": True, "source": "fallback: overrides + interaction"}
    sources = collect_edges(rules, links)
    kept, rejected = filter_edges(rules, anns, set(sources))
    for e in rejected:
        e["sources"] = sources.get((e["winner"], e["loser"]), [])
    pairs = set(graph[1]) | set(links.get("uncertain", set())) | set(links.get("conflicts", set()))
    kept_pairs, rejected_pairs = filter_pairs(rules, anns, pairs)
    _PREC_CACHE[key] = {"annotations": anns, "edges": kept, "pairs": kept_pairs, "rejected_edges": rejected,
                        "rejected_pairs": rejected_pairs}
    return _PREC_CACHE[key]


def verdicts_for_building(b, rules, as_of=DEFAULT_AS_OF, links=None, details=None, log=None, annotations=None):
    from .precedence import apply_precedence
    if annotations is not None:
        rules = [dict(r, _annotation=annotations.get(r["team_rule_id"])) for r in rules]
    links = links if links is not None else current_links()
    as_of_d = to_date(as_of)
    _resolve_references(b, rules, as_of_d)
    raw = {r["team_rule_id"]: base_verdict(b, r, as_of_d) for r in rules}
    base = {rid: (v if v and v.get("result") else None) for rid, v in raw.items()}
    by_id = {r["team_rule_id"]: r for r in rules}
    active = {rid for rid, v in base.items() if v and v["result"] in ACTIVE}
    pc = precedence_context(rules, links)
    res, plog = apply_precedence(base, rules, pc["annotations"], b, as_of_d, edges=pc["edges"])
    if log is not None:
        log.extend(plog)
    why_omitted = {x["team_rule_id"]: x["reason"] for x in plog if x["action"].startswith(("omitted", "modifies"))}
    out = []
    for rid in by_id:
        v = res.get(rid)
        if v is None:
            if details is not None:
                details[rid] = {"omit_reason": why_omitted.get(rid) or (raw[rid] or {}).get("omit_reason")}
            continue
        rule = by_id[rid]
        date_conflict = (rule.get("_annotation") or {}).get("date_conflict_note")
        intrinsic_conflict = _intrinsic_conflict(rule)
        contract_conflict = _contract_conflict(rid, res, by_id)
        entry = {"team_rule_id": rid, "result": v["result"], "explanation": v["explanation"],
                 "conflict_flag": intrinsic_conflict or bool(v.get("conflict_with")) or
                                  bool(date_conflict) or bool(contract_conflict)}
        if intrinsic_conflict and rule.get("conflict_note"):
            entry["explanation"] += f" Conflict flagged: {rule['conflict_note']}"
        if date_conflict:
            entry["explanation"] += f" Date conflict flagged: {date_conflict}"
        if contract_conflict:
            entry["explanation"] += f" Part 1 conflict classification: {contract_conflict}."
        if rid in active:
            others = sorted(o for o in active if o != rid and frozenset((rid, o)) in pc["pairs"])
            if others:
                entry["conflict_flag"] = True
                entry["explanation"] += (" Possible conflict for human review with "
                                         + ", ".join(f"{by_id[o]['title']} ({o})" for o in others) + ".")
                why = [UNCERTAIN_REASONS[frozenset((rid, o))] for o in others if frozenset((rid, o)) in UNCERTAIN_REASONS]
                if why:
                    entry["explanation"] += " Override audit: " + " ".join(w for w in why if w)
        out.append(entry)
        if details is not None:
            details[rid] = {"missing_facts": list(v.get("missing_facts") or []) if v["result"] == "unknown" else []}
        for d in rule.get("_duplicates") or []:
            out.append({**entry, "team_rule_id": d["team_rule_id"],
                        "explanation": f"Same obligation as {rule['title']} ({rid}), extracted from another source "
                                       f"({d.get('source_doc_id')}, {d.get('citation')}); same verdict. "
                                       + entry["explanation"]})
            if details is not None:
                details[d["team_rule_id"]] = dict(details[rid])
    return out


def lookups(buildings, rules, as_of=DEFAULT_AS_OF, links=None, details=None, log=None):
    links = links if links is not None else current_links()
    out = {}
    for aid, b in sorted(buildings.items()):
        d = {} if details is not None else None
        out[aid] = verdicts_for_building(b, rules, as_of, links, d, log)
        if details is not None:
            details[aid] = d
    return out
