import argparse
import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS = Path(__file__).resolve().parent / "rule_annotations.json"
TEXT_DIRS = [ROOT / "starter pack" / "corpus" / "text", ROOT / "corpus_extra"]
MANIFESTS = [ROOT / "starter pack" / "corpus" / "corpus_manifest.csv", ROOT / "corpus_extra" / "manifest_extra.csv",
             ROOT / "corpus_extra" / "corpus_manifest.csv"]
HASH_FIELDS = ("title", "requirement", "interaction", "coverage_conditions", "exemptions", "quoted_span", "citation",
               "category", "jurisdiction", "level")
FLAGS = ("yields_to_local", "supersedes_state", "may_preempt_local", "modifies_local", "bars_local_cap",
         "period_figure", "amends_existing_law", "event_only", "secondary_source", "supersedes_same_level")
VALUED = ("construction_cutoff",)
DEFAULT = {**{f: False for f in FLAGS}, "construction_cutoff": None, "modifies_local_test": None,
           "modifies_local_missing_fact": None, "modifies_local_category": None, "in_force_since": None,
           "supersedes_same_level_citations": [], "date_conflict_note": None, "evidence": {}}
REACHES_LOCAL = {"applies", "unknown"}
REACHES_STATE = {"applies", "unknown"}
IN_FORCE = {"applies", "unknown"}



def rule_hash(rule):
    return hashlib.sha256(json.dumps({k: rule.get(k) for k in HASH_FIELDS}, sort_keys=True).encode()).hexdigest()[:16]


def annotation_key(rule):
    return f"{rule['team_rule_id']}:{rule_hash(rule)}"


def _read(path):
    return json.loads(path.read_text()) if path.exists() else {"annotations": {}}


def load_annotations(rules, raw_rules=None, path=ANNOTATIONS):
    stored = _read(path).get("annotations", {})
    raw = {r["team_rule_id"]: r for r in (raw_rules or rules)}
    out, missing = {}, []
    for r in rules:
        rid = r["team_rule_id"]
        a = stored.get(annotation_key(raw.get(rid, r)))
        if a is None:
            missing.append(rid)
            out[rid] = dict(DEFAULT, evidence={})
        else:
            out[rid] = {**DEFAULT, **{k: v for k, v in a.items() if k in DEFAULT}}
    return out, sorted(missing)


def _norm(t):
    return " ".join((t or "").split()).lower()


_TEXT_CACHE = {}


def corpus_text(doc_id):
    if doc_id not in _TEXT_CACHE:
        p = next((d / f"{doc_id}.txt" for d in TEXT_DIRS if (d / f"{doc_id}.txt").exists()), None)
        _TEXT_CACHE[doc_id] = _norm(p.read_text(errors="replace")) if p else None
    return _TEXT_CACHE[doc_id]


def manifest_types():
    out = {}
    for m in MANIFESTS:
        if m.exists():
            with open(m, newline="") as f:
                for row in csv.DictReader(f):
                    out.setdefault(row["doc_id"], row.get("source_type") or "")
    return out


def is_secondary_type(source_type):
    st = (source_type or "").lower()
    return not st.startswith("official") or "mirror" in st


def _check_one(ev, field, types):
    if not isinstance(ev, dict) or not ev.get("doc_id"):
        return "evidence has no doc_id"
    if field == "secondary_source":
        st = types.get(ev["doc_id"])
        if st is None:
            return f"{ev['doc_id']} not in any corpus manifest"
        if ev.get("manifest_source_type") != st or not is_secondary_type(st):
            return f"manifest source_type of {ev['doc_id']} is {st!r}"
        return None
    text = corpus_text(ev["doc_id"])
    if text is None:
        return f"no corpus text for {ev['doc_id']}"
    if not _norm(ev.get("quote")) or _norm(ev.get("quote")) not in text:
        return f"quote not found verbatim in {ev['doc_id']}: {(ev.get('quote') or '')[:80]!r}"
    return None


def verify_annotation(a, types=None):
    types = types if types is not None else manifest_types()
    a = {**DEFAULT, **a, "evidence": dict(a.get("evidence") or {})}
    rejects = []
    for field in FLAGS + VALUED:
        if not a.get(field):
            continue
        evs = a["evidence"].get(field)
        evs = evs if isinstance(evs, list) else [evs] if evs else []
        why = "no evidence" if not evs else next((w for w in (_check_one(e, field, types) for e in evs) if w), None)
        if why:
            rejects.append({"field": field, "reason": why})
            a[field] = None if field in VALUED else False
            a["evidence"].pop(field, None)
    if a["modifies_local"] and not (a.get("modifies_local_test") and a.get("modifies_local_missing_fact")):
        rejects.append({"field": "modifies_local", "reason": "no modifies_local_test or missing fact"})
        a["modifies_local"] = False
    if a["supersedes_same_level"] and not a.get("supersedes_same_level_citations"):
        rejects.append({"field": "supersedes_same_level", "reason": "no target citation"})
        a["supersedes_same_level"] = False
    if a["amends_existing_law"] and a.get("in_force_since") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a["in_force_since"]):
        rejects.append({"field": "in_force_since", "reason": f"not a date: {a['in_force_since']!r}"})
        a["in_force_since"] = None
    if not a["amends_existing_law"]:
        a["in_force_since"] = None
    if a["yields_to_local"] and a["may_preempt_local"]:
        rejects.append({"field": "may_preempt_local", "reason": "yields_to_local and may_preempt_local are exclusive"})
        a["may_preempt_local"] = False
        a["evidence"].pop("may_preempt_local", None)
    return a, rejects


def verify_annotations(path=ANNOTATIONS, rules=None, write=True):
    data = _read(path)
    types = manifest_types()
    rejects, out = [], {}
    for key, a in sorted(data.get("annotations", {}).items()):
        v, rej = verify_annotation(a, types)
        out[key] = v
        rejects += [{"key": key, **r} for r in rej]
    data["annotations"] = out
    data["verification"] = {"checked": len(out), "rejects": rejects}
    if rules is not None:
        data["verification"]["rules_without_annotation"] = sorted(r["team_rule_id"] for r in rules
                                                                  if annotation_key(r) not in out)
    if write:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return data["verification"]



def to_date(s):
    if s is None or isinstance(s, date):
        return s
    parts = str(s).split("-") + ["01", "01"]
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def _years_before(d, n):
    try:
        return d.replace(year=d.year - n)
    except ValueError:
        return d.replace(year=d.year - n, day=28)


def _cmp(a, op, b):
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b}[op]


def _interval_test(lo, hi, op, v):
    if op == "==":
        return (lo == hi == v) if lo is not None and lo == hi else (False if (lo is not None and lo > v) or
                                                                     (hi is not None and hi < v) else None)
    all_ok = {">": lo is not None and lo > v, ">=": lo is not None and lo >= v,
              "<": hi is not None and hi < v, "<=": hi is not None and hi <= v}[op]
    none_ok = {">": hi is not None and hi <= v, ">=": hi is not None and hi < v,
               "<": lo is not None and lo >= v, "<=": lo is not None and lo > v}[op]
    return True if all_ok else False if none_ok else None


def co_interval(b):
    lo, hi = to_date(b.get("co_date_min")), to_date(b.get("co_date_max"))
    y = b.get("year_built")
    if y is not None:
        lo, hi = lo or date(y, 1, 1), hi or date(y, 12, 31)
    if hi is None and b.get("year_built_max") is not None:
        hi = date(b["year_built_max"], 12, 31)
    return lo, hi


def eval_test(b, test, as_of):
    if "all" in test or "any" in test:
        vals = [eval_test(b, t, as_of) for t in test.get("all") or test.get("any")]
        if "all" in test:
            return False if False in vals else True if all(v is True for v in vals) else None
        return True if True in vals else False if all(v is False for v in vals) else None
    fact, op = test["fact"], test["op"]
    v = test.get("value")
    if test.get("value_years_before_as_of") is not None:
        v = _years_before(to_date(as_of), int(test["value_years_before_as_of"]))
    if fact == "certificate_of_occupancy_date":
        lo, hi = co_interval(b)
        return None if lo is None and hi is None else _interval_test(lo, hi, op, to_date(v))
    if fact == "year_built" and isinstance(v, date):
        v = v.year
    if fact == "units" and b.get("units") is None:
        lo, hi = b.get("units_min"), b.get("units_max")
        return None if lo is None and hi is None else _interval_test(lo, hi, op, v)
    val = b.get(fact)
    return None if val is None else _cmp(val, op, v)



def rule_state(rule):
    j = rule.get("jurisdiction") or ""
    return j if rule.get("level") == "state" else j.rsplit(", ", 1)[-1]


def is_local_of(rule, state):
    return rule.get("level") == "city" and (rule.get("jurisdiction") or "").endswith(f", {state}")


def is_cap_rule(rule, annotation):
    from .prepare import is_ma_40p
    return (rule.get("category") == "rent_increase_limits"
            and not is_ma_40p(rule)
            and not (annotation or {}).get("bars_local_cap"))


def _cutoff(rule, ann):
    c = rule.get("coverage_conditions")
    if isinstance(c, dict):
        if c.get("built_on_or_before") and not c.get("built_after"):
            return "old", to_date(c["built_on_or_before"])
        if c.get("built_after") and not c.get("built_on_or_before"):
            return "new", to_date(c["built_after"])
        for p in c.get("all") or []:
            if isinstance(p, dict) and p.get("fact") in ("certificate_of_occupancy_date", "year_built"):
                if p.get("op") in ("<", "<="):
                    return "old", to_date(p["value"]) if p.get("fact") != "year_built" else date(int(p["value"]), 12, 31)
                if p.get("op") in (">", ">="):
                    return "new", to_date(p["value"]) if p.get("fact") != "year_built" else date(int(p["value"]), 12, 31)
    cut = (ann or {}).get("construction_cutoff")
    if cut and cut.get("date"):
        return ("old" if cut.get("covered_if") in ("on_or_before", "before") else "new"), to_date(cut["date"])
    return None


def complementary(rules, annotations):
    sides = {}
    for r in rules:
        c = _cutoff(r, annotations.get(r["team_rule_id"]))
        if c:
            sides.setdefault(c[1], set()).add(c[0])
    return any(s == {"old", "new"} for s in sides.values())


def _place_confirmed(b, city):
    return b.get("legal_city") == city and b.get("city_status") not in ("postal_fallback", "postal_only")


def _rule_live_for(rule, b, as_of):
    if b.get("state") != rule_state(rule):
        return False
    from .temporal import time_status
    return time_status(rule, rule.get("_annotation"), as_of)[0] == "in_force"


def _name(rule):
    return f"{rule['title']} ({rule['team_rule_id']})"


def _missing(entry):
    return list((entry or {}).get("missing_facts") or [])



def apply_precedence(base_results, rules, annotations, building, as_of, edges=None):
    by = {r["team_rule_id"]: r for r in rules}
    ann = lambda rid: annotations.get(rid) or DEFAULT
    res = {rid: (dict(v) if v else None) for rid, v in base_results.items()}
    aid = building.get("address_id")
    log = []

    def note(rid, action, reason, by_id=None):
        log.append({"address_id": aid, "team_rule_id": rid, "action": action, "by": by_id, "reason": reason})

    for rid in sorted(res):
        a, rule = ann(rid), by.get(rid)
        if rule is None or not a.get("modifies_local"):
            continue
        if res[rid] is not None:
            res[rid] = None
            note(rid, "modifies_local_not_listed", "exempts buildings from local rules instead of governing the "
                 "lease; applied to the local rules of its category, never listed alone")
        if not _rule_live_for(rule, building, as_of):
            continue
        cat = a.get("modifies_local_category") or rule["category"]
        t = eval_test(building, a["modifies_local_test"], as_of)
        if t is False:
            continue
        for lid in sorted(res):
            lr, le = by.get(lid), res[lid]
            if le is None or lr is None or lr["category"] != cat or not is_local_of(lr, rule_state(rule)):
                continue
            if t is True:
                res[lid] = None
                note(lid, "omitted_by_modifies_local", f"exempt from local {cat.replace('_', ' ')} rules under "
                     f"{_name(rule)}: {a['modifies_local_missing_fact']} holds for this building", rid)
            elif le["result"] in IN_FORCE:
                le["result"] = "unknown"
                le["explanation"] = (f"{lr['title']} covers this building unless it is exempt under {_name(rule)}, "
                                     f"which depends on facts not in the data ({a['modifies_local_missing_fact']}). "
                                     + le["explanation"])
                le["missing_facts"] = _missing(le) + [a["modifies_local_missing_fact"]]
                note(lid, "unknown_by_modifies_local", f"{a['modifies_local_missing_fact']} is not in the data", rid)

    for rid in sorted(res):
        e, rule = res[rid], by.get(rid)
        if e is None or rule is None or rule["level"] != "state" or not ann(rid).get("yields_to_local") \
                or e["result"] not in IN_FORCE:
            continue
        gov = sorted(lid for lid, le in res.items() if le is not None and lid in by and lid != rid
                     and by[lid]["category"] == rule["category"] and is_local_of(by[lid], rule["jurisdiction"])
                     and ann(lid).get("supersedes_state"))
        applies = [lid for lid in gov if res[lid]["result"] == "applies"]
        unknown = [lid for lid in gov if res[lid]["result"] == "unknown" and not by[lid].get("_inherited_from")]
        if applies:
            lid = applies[0]
            e.update(result="superseded", superseded_by=lid,
                     explanation=f"Covered, but {_name(by[lid])} governs: {rule['title']} yields to a more "
                                 f"protective local rule of the same category.")
            e.pop("missing_facts", None)
            note(rid, "superseded", "yields_to_local; local supersedes_state rule applies", lid)
            continue
        if not unknown:
            continue
        cities = {by[lid]["jurisdiction"] for lid in unknown}
        if len(cities) == 1 and _place_confirmed(building, next(iter(cities))) and \
                complementary([by[lid] for lid in unknown], annotations):
            e.update(result="superseded", superseded_by=unknown[0],
                     explanation=f"Covered, but one of the complementary local ordinances "
                                 f"{', '.join(_name(by[lid]) for lid in unknown)} governs every building (which one "
                                 f"depends on the construction date); {rule['title']} yields.")
            e.pop("missing_facts", None)
            note(rid, "superseded_complementary", "local supersedes_state rules split all buildings at one "
                 "construction date", unknown[0])
            continue
        lid = sorted(unknown, key=lambda x: (not _missing(res[x]), x))[0]
        e.update(result="unknown",
                 explanation=f"Yields to {_name(by[lid])}, whose coverage of this building is unknown, so this rule "
                             f"applies only if that one does not: {res[lid]['explanation']}")
        e["missing_facts"] = _missing(res[lid])
        note(rid, "unknown_cascade", "yields_to_local; best local supersedes_state rule is unknown", lid)

    for w, l in sorted(edges or ()):
        we, le = res.get(w), res.get(l)
        if we is None or le is None or le["result"] not in IN_FORCE or w not in by or l not in by:
            continue
        if we["result"] == "applies":
            le.update(result="superseded", superseded_by=w, explanation=f"Covered, but {_name(by[w])} governs.")
            le.pop("missing_facts", None)
            note(l, "superseded", "kept supersession edge", w)
        elif we["result"] == "unknown" and le["result"] == "applies" and not by[w].get("_inherited_from"):
            le.update(result="unknown", explanation=f"Yields to {_name(by[w])}, whose coverage of this building is "
                                                    f"unknown, so this rule applies only if that one does not: "
                                                    f"{we['explanation']}")
            le["missing_facts"] = _missing(we)
            note(l, "unknown_cascade", "kept supersession edge; winner unknown", w)

    for rid in sorted(res):
        e, rule, a = res[rid], by.get(rid), ann(rid)
        if e is None or rule is None or rule["level"] != "state" or not a.get("may_preempt_local"):
            continue
        if a.get("yields_to_local"):
            note(rid, "may_preempt_ignored", "a yields_to_local rule cannot preempt local rules")
            continue
        if e["result"] not in REACHES_STATE:
            continue
        locs = sorted(lid for lid, le in res.items() if le is not None and lid in by
                      and by[lid]["category"] == rule["category"] and is_local_of(by[lid], rule["jurisdiction"])
                      and le["result"] in REACHES_LOCAL)
        for lid in locs:
            for x, y in ((rid, lid), (lid, rid)):
                cw = res[x].setdefault("conflict_with", [])
                if y not in cw:
                    cw.append(y)
                    cw.sort()
                    res[x]["explanation"] += (f" Possible conflict for human review with {_name(by[y])}: the state "
                                              f"law may preempt local {rule['category'].replace('_', ' ')} rules.")
            note(lid, "conflict", "may_preempt_local state rule and local rule both reach the building", rid)
    return res, log



def _cite(c):
    return re.sub(r"[^a-z0-9.()]", "", (c or "").lower())


def _explicit(w, l, a):
    return bool(a.get("supersedes_same_level")) and any(_cite(t) and _cite(t) in _cite(l.get("citation"))
                                                         for t in a.get("supersedes_same_level_citations") or [])


def edge_reason(rules_by, annotations, w, l):
    if w not in rules_by or l not in rules_by:
        return "rule id not in rules"
    if w == l:
        return "self edge"
    W, L = rules_by[w], rules_by[l]
    aw, al = annotations.get(w) or DEFAULT, annotations.get(l) or DEFAULT
    if W["category"] != L["category"]:
        return f"different categories ({W['category']} vs {L['category']}): never supersession"
    if rule_state(W) != rule_state(L):
        return "different states"
    if aw.get("modifies_local"):
        return "winner is modifies_local: applied to local rules by B5, not as a supersession"
    if aw.get("event_only"):
        return "winner only plays at an event (event_only): an event carve-out coexists with the other rule"
    if W["level"] == "city" and L["level"] == "state":
        if al.get("yields_to_local") and aw.get("supersedes_state"):
            return None
        miss = [f for f, a in (("loser yields_to_local", al.get("yields_to_local")),
                               ("winner supersedes_state", aw.get("supersedes_state"))) if not a]
        return "local over state needs both annotations: missing " + " and ".join(miss)
    if W["level"] == "state" and L["level"] == "city":
        if aw.get("may_preempt_local"):
            return "winner may_preempt_local: possible preemption is a conflict for human review (B3), not supersession"
        return None
    if W["level"] == "city" and W["jurisdiction"] != L["jurisdiction"]:
        return "local rules of different cities"
    if _explicit(W, L, aw):
        return None
    if W["level"] == "state":
        return "two state rules: no verified corpus passage says one replaces the other"
    return "two local rules of the same city: no verified corpus passage says one replaces the other"


def filter_edges(rules, annotations, edges):
    by = {r["team_rule_id"]: r for r in rules}
    kept, rejected = set(), []
    for w, l in sorted(edges):
        why = edge_reason(by, annotations, w, l)
        if why is None:
            kept.add((w, l))
        else:
            rejected.append({"winner": w, "loser": l, "reason": why})
    return kept, rejected


def filter_pairs(rules, annotations, pairs):
    by = {r["team_rule_id"]: r for r in rules}
    kept, rejected = set(), []
    for p in sorted(pairs, key=sorted):
        x, y = sorted(p)
        if x not in by or y not in by:
            rejected.append({"pair": [x, y], "reason": "rule id not in rules"})
            continue
        X, Y = by[x], by[y]
        ax, ay = annotations.get(x) or DEFAULT, annotations.get(y) or DEFAULT
        why = None
        if X["category"] != Y["category"]:
            why = "different categories"
        elif ax.get("modifies_local") or ay.get("modifies_local"):
            why = "settled by modifies_local (B5)"
        elif (ax.get("yields_to_local") and ay.get("supersedes_state")) or \
                (ay.get("yields_to_local") and ax.get("supersedes_state")):
            why = "settled by yields_to_local / supersedes_state (B1)"
        elif ax.get("may_preempt_local") or ay.get("may_preempt_local"):
            why = "flagged by may_preempt_local (B3)"
        if why:
            rejected.append({"pair": [x, y], "reason": why})
        else:
            kept.add(frozenset((x, y)))
    return kept, rejected


def collect_edges(rules, links=None):
    from .links import current_links
    from .verdict import override_graph
    links = links if links is not None else current_links()
    out = {}
    for e in override_graph(rules)[0]:
        out.setdefault(e, []).append("overrides/interaction/audit")
    for e in links.get("supersedes", set()):
        out.setdefault(tuple(e), []).append("links.json")
    return out


def summarize_log(records):
    counts = {}
    for r in records:
        k = f"{r['action']}|{r['team_rule_id']}" + (f"|by {r['by']}" if r.get("by") else "")
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items()))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="check every evidence quote; failing fields become false")
    args = ap.parse_args(argv)
    if not args.verify:
        ap.print_help()
        return
    from .rules import load_rules
    rules, source, _ = load_rules(fetch=False)
    v = verify_annotations(rules=rules)
    for r in v["rejects"]:
        print(f"REJECT {r['key']} {r['field']}: {r['reason']}")
    print(f"verified {v['checked']} annotations, {len(v['rejects'])} rejected field(s); rules without annotation "
          f"for their current text ({source}): {v.get('rules_without_annotation') or 'none'}")


if __name__ == "__main__":
    main()
