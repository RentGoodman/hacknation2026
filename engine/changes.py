import copy
import json
from collections import Counter
from pathlib import Path

from engine.verdict import lookups

TESTS_PATH = Path(__file__).resolve().parent.parent / "starter pack" / "dev" / "change_tests.json"
RENT = "rent_increase_limits"


def _jurisdiction_codes(jurisdiction):
    place = (jurisdiction or "").split(",", 1)[0].strip()
    words = [w for w in place.replace("-", " ").split() if w]
    return {place.upper(), "".join(w[0] for w in words).upper(), words[0][:3].upper()} if words else set()


def _category_codes(category):
    words = [w for w in (category or "").split("_") if w]
    return {words[0].upper(), words[0][:3].upper(), "".join(w[0] for w in words).upper()} if words else set()


def _matches_test_id(rule, test_rule_id, test):
    parts = test_rule_id.upper().split("-")
    if len(parts) < 2 or parts[0] not in _jurisdiction_codes(rule.get("jurisdiction")):
        return False
    if parts[1] not in _category_codes(rule.get("category")):
        return False
    states = set(test.get("states") or [])
    state = (rule.get("jurisdiction") or "").rsplit(", ", 1)[-1]
    if states and state not in states:
        return False
    if test.get("type") == "pending" and rule.get("status") != "pending":
        return False
    if test.get("type") == "negative" and rule.get("status") != "failed":
        return False
    return True


def map_test_rules(rules, tests=None):
    tests = tests or json.loads(TESTS_PATH.read_text())
    return {tid: sorted(r["team_rule_id"] for r in rules if _matches_test_id(r, tid, test))
            for test in tests for tid in test["rule_ids"]}


def petition_25_21_ids(rules):
    mapped = set(map_test_rules(rules).get("MA-RENT-P1", []))
    named = {r["team_rule_id"] for r in rules
             if "25-21" in " ".join(str(r.get(k) or "") for k in ("title", "citation", "requirement"))}
    return mapped | named


def _restricted(lk, ids):
    ids = set(ids)
    return {aid: {e["team_rule_id"]: e["result"] for e in ents if e["team_rule_id"] in ids}
            for aid, ents in lk.items()}


def _diff(buildings, rules, ids, before, after):
    a = _restricted(lookups(buildings, rules, before), ids)
    b = _restricted(lookups(buildings, rules, after), ids)
    changed = []
    for aid in buildings:
        ra, rb = a.get(aid, {}), b.get(aid, {})
        if any(ra.get(i, "omitted") != rb.get(i, "omitted") for i in ids):
            changed.append(aid)
    return sorted(changed)


def _transition(buildings, rules, ids, before, after, frm="not_yet_effective", to="applies"):
    a = _restricted(lookups(buildings, rules, before), ids)
    b = _restricted(lookups(buildings, rules, after), ids)
    hit, pairs = [], Counter()
    for aid in sorted(buildings):
        for i in sorted(ids):
            pa, pb = a.get(aid, {}).get(i, "omitted"), b.get(aid, {}).get(i, "omitted")
            pairs[(pa, pb)] += 1
            if pa == frm and pb == to and aid not in hit:
                hit.append(aid)
    return hit, pairs


def _pairs_note(pairs):
    return "; ".join(f"{a} -> {b}: {n}" for (a, b), n in sorted(pairs.items()))


def _city(b):
    return b.get("legal_city") or b.get("legal_city_candidate")


def _mapping_note(test, mapping):
    parts, unmapped = [], []
    for t in test["rule_ids"]:
        ids = mapping.get(t, [])
        if ids:
            parts.append(f"{t} maps to {', '.join(ids)}")
        else:
            unmapped.append(t)
    s = "Mapping: " + ("; ".join(parts) if parts else "none") + "."
    if unmapped:
        s += " Unmapped test rules: " + ", ".join(unmapped) + "."
    return s


def build_changes(buildings, rules):
    if not any(r.get("_precedence") is not None for r in rules):
        from engine.precedence import load_annotations
        annotations, _ = load_annotations(rules, rules)
        rules = [dict(r, _precedence=annotations[r["team_rule_id"]]) for r in rules]
    tests = {t["test_id"]: t for t in json.loads(TESTS_PATH.read_text())}
    mapping = map_test_rules(rules, list(tests.values()))
    by_id = {r["team_rule_id"]: r for r in rules}
    out = {}

    def ids_for(*tids):
        return sorted({i for t in tids for i in mapping.get(t, [])})

    t = tests["T1"]
    ids = ids_for(*t["rule_ids"])
    aff, pairs = _transition(buildings, rules, ids, t["as_of_before"], t["as_of_after"])
    states = Counter(buildings[a]["state"] for a in aff)
    out["T1"] = {"affected_address_ids": aff, "conflict_flag_address_ids": [],
                 "notes": f"{_mapping_note(t, mapping)} Affected = addresses whose mapped rule goes from "
                          f"not_yet_effective on {t['as_of_before']} to applies on {t['as_of_after']}: {len(aff)} "
                          f"(by state: {dict(sorted(states.items()))}). Verdict pairs per (address, rule): "
                          f"{_pairs_note(pairs)}."}

    t = tests["T2"]
    boundary_ids = set(ids_for(*t["rule_ids"]))
    jurisdiction_by_rule = {rid: by_id[rid]["jurisdiction"] for rid in boundary_ids}
    lk = lookups(buildings, rules, t["as_of"])
    aff, unknown, counts, res = [], [], Counter(), Counter()
    for aid in sorted(lk):
        city = _city(buildings[aid])
        for e in lk[aid]:
            rid = e["team_rule_id"]
            if rid not in boundary_ids:
                continue
            own = jurisdiction_by_rule[rid]
            if city != own:
                raise AssertionError(f"T2: {own} rule {rid} hit outside {own} at {aid} ({city})")
            res[(own, e["result"])] += 1
            if e["result"] == "applies" and aid not in aff:
                aff.append(aid)
                counts[own] += 1
            elif e["result"] == "unknown" and aid not in unknown:
                unknown.append(aid)
    unknown = [a for a in unknown if a not in aff]
    count_note = ", ".join(f"{place} {counts[place]}" for place in sorted(set(jurisdiction_by_rule.values())))
    out["T2"] = {"affected_address_ids": sorted(aff), "conflict_flag_address_ids": [],
                 "notes": f"{_mapping_note(t, mapping)} Affected = addresses where a mapped local rule's result is "
                          f"applies inside that rule's jurisdiction on {t['as_of']}: {count_note or 'none'}. "
                          f"Unknown (not counted): {', '.join(unknown) or 'none'}. "
                          f"Results per city: {', '.join(f'{c} {r} {n}' for (c, r), n in sorted(res.items()))}. "
                          "Checked that every mapped local-rule hit stays inside its declared jurisdiction."}

    t = tests["T3"]
    nj = ids_for(*t["rule_ids"])
    aff, pairs3 = _transition(buildings, rules, nj, t["as_of_before"], t["as_of_after"])
    conflict_ids = ids_for(*(t.get("conflict_with") or []))
    flag_ids = set(nj) | set(conflict_ids)
    lk = lookups(buildings, rules, t["as_of_after"])
    conf = sorted(a for a, ents in lk.items()
                  if any(e["team_rule_id"] in flag_ids and e.get("conflict_flag") for e in ents))
    out["T3"] = {"affected_address_ids": aff, "conflict_flag_address_ids": conf,
                 "notes": f"{_mapping_note(t, mapping)} Compared results on {t['as_of_before']} and "
                          f"{t['as_of_after']}; affected = not_yet_effective -> applies: {len(aff)} addresses "
                          f"(verdict pairs: {_pairs_note(pairs3)}). On {t['as_of_after']}, "
                          f"{len(conf)} addresses carry a conflict flag on a mapped rule or a rule declared in "
                          f"conflict_with ({', '.join(t.get('conflict_with') or []) or 'none'}), for human review "
                          "of possible preemption."}

    t = tests["T4"]
    ma = ids_for(*t["rule_ids"])
    sim = copy.deepcopy(rules)
    for r in sim:
        if r["team_rule_id"] in ma:
            r["status"] = "in_force"
            r["effective_date"] = t["as_of"]
    lk_sim = lookups(buildings, sim, t["as_of"])
    aff = sorted(a for a, ents in lk_sim.items()
                 if any(e["team_rule_id"] in ma and e["result"] in ("applies", "unknown") for e in ents))
    lk_real = _restricted(lookups(buildings, rules, t["as_of"]), ma)
    all_pending = all(lk_real[a] and all(v == "pending" for v in lk_real[a].values()) for a in aff)
    out["T4"] = {"affected_address_ids": aff, "conflict_flag_address_ids": [],
                 "notes": f"{_mapping_note(t, mapping)} Simulated enactment (status in force, effective {t['as_of']}); "
                          f"{len(aff)} addresses would be covered. With the real rules on {t['as_of']}, "
                          + ("every one of these addresses reports the bills as pending, not in force."
                             if all_pending else "some of these addresses do not report pending; review needed.")}

    t = tests["T5"]
    petition = petition_25_21_ids(rules)
    lk = lookups(buildings, rules, t["as_of"])
    bad = ("applies", "unknown", "superseded", "not_yet_effective")
    states = set(t.get("states") or [])
    for aid, ents in lk.items():
        b = buildings[aid]
        if not states or b.get("state") in states:
            for e in ents:
                if e["team_rule_id"] in petition and e["result"] in bad:
                    raise AssertionError(f"T5: petition 25-21 reported for {aid} via {e['team_rule_id']}")
    statuses = ", ".join(f"{i} status {by_id[i].get('status')}" for i in ids_for("MA-RENT-P1"))
    out["T5"] = {"affected_address_ids": [], "conflict_flag_address_ids": [],
                 "notes": f"{_mapping_note(t, mapping)} {statuses or 'No mapped rule'}; a failed rule is omitted "
                          "from every lookup. Checked only petition 25-21; unrelated present or future rent laws do "
                          "not belong to this guard."}
    return out


def change_property_errors(buildings, rules, changes):
    actual = lambda t, field="affected_address_ids": set(changes.get(t, {}).get(field, []))
    mapping = map_test_rules(rules)
    by_id = {r["team_rule_id"]: r for r in rules}
    t2_places = {
        by_id[rid]["jurisdiction"]
        for test_id in ("HOB-ALG-01", "JC-ALG-01")
        for rid in mapping.get(test_id, [])
    }
    expected = {
        "T1": {a for a, b in buildings.items() if b.get("state") == "CA"},
        "T2": {a for a, b in buildings.items() if b.get("legal_city") in t2_places},
        "T3": {a for a, b in buildings.items() if b.get("state") == "NJ"},
        "T4": {a for a, b in buildings.items() if b.get("state") == "MA"},
        "T5": set(),
    }
    errors = []
    for tid, want in expected.items():
        got = actual(tid)
        if got != want:
            errors.append(f"{tid} affected mismatch: expected {len(want)}, got {len(got)}")
    t3_conf = {a for a, b in buildings.items()
               if (b.get("legal_city") or b.get("legal_city_candidate")) in
               ("Hoboken, NJ", "Jersey City, NJ")}
    if actual("T3", "conflict_flag_address_ids") != t3_conf:
        errors.append(f"T3 conflict mismatch: expected {len(t3_conf)}, got "
                      f"{len(actual('T3', 'conflict_flag_address_ids'))}")
    return errors
