import copy
import hashlib
import json
from pathlib import Path

import pytest

from engine.changes import build_changes, change_property_errors, map_test_rules
from engine.rules import load_buildings
from engine.run import assert_t5, evaluation_rules
from engine.verdict import lookups


@pytest.fixture(scope="module")
def data():
    b = load_buildings()
    rules = evaluation_rules(fetch=False)
    return b, rules, build_changes(b, rules)


def require_mapped(rules, *test_ids):
    m = map_test_rules(rules)
    missing = [t for t in test_ids if not m.get(t)]
    if missing:
        pytest.skip(f"rules.json has no rule for {missing}: data gap in Part 1, reported in changes.json notes")


def ids(b, pred):
    return sorted(a for a, x in b.items() if pred(x))


def city(x):
    return x["legal_city"] or x.get("legal_city_candidate")


def test_t1_all_ca(data):
    b, _, c = data
    assert c["T1"]["affected_address_ids"] == ids(b, lambda x: x["state"] == "CA")


def test_t2_boundary(data):
    b, rules, c = data
    require_mapped(rules, "HOB-ALG-01", "JC-ALG-01")
    aff = set(c["T2"]["affected_address_ids"])
    by_id = {r["team_rule_id"]: r for r in rules}
    mapping = map_test_rules(rules)
    mapped_places = {
        by_id[rid]["jurisdiction"]
        for test_id in ("HOB-ALG-01", "JC-ALG-01")
        for rid in mapping[test_id]
    }
    assert aff == set(ids(b, lambda x: x["legal_city"] in mapped_places))
    assert not aff & set(ids(b, lambda x: city(x) == "Newark, NJ"))
    for a in ids(b, lambda x: (x["city_status"] == "postal_only" or x["legal_city"] not in mapped_places)
                 and city(x) in ("Hoboken, NJ", "Jersey City, NJ")):
        assert a in c["T2"]["notes"]


def test_t3_nj_and_conflicts(data):
    b, rules, c = data
    assert c["T3"]["affected_address_ids"] == ids(b, lambda x: x["state"] == "NJ")
    require_mapped(rules, "HOB-ALG-01", "JC-ALG-01")
    assert set(c["T3"]["conflict_flag_address_ids"]) == set(ids(b, lambda x: city(x) in ("Hoboken, NJ", "Jersey City, NJ")))


def test_t4_all_ma_still_pending(data):
    b, rules, c = data
    ma = ids(b, lambda x: x["state"] == "MA")
    assert c["T4"]["affected_address_ids"] == ma
    L = lookups(b, rules, "2026-10-01")
    for a in ma:
        assert any(e["result"] == "pending" for e in L[a])


def test_t5_empty_and_failed_petition_absent(data):
    b, rules, c = data
    assert c["T5"]["affected_address_ids"] == []
    petition = set(map_test_rules(rules)["MA-RENT-P1"])
    L = lookups(b, rules, "2026-10-01")
    for a in ids(b, lambda x: city(x) in ("Boston, MA", "Cambridge, MA")):
        assert not [e for e in L[a] if e["team_rule_id"] in petition]


def test_t1_t2_are_transitions_not_presence(data):
    import copy
    b, rules, _ = data
    m = map_test_rules(rules)
    hostile = copy.deepcopy(rules)
    for r in hostile:
        if r["team_rule_id"] in set(m["CA-ALG-01"]) | set(m["JC-ALG-01"]):
            r["coverage_conditions"] = "free text that is not machine readable"
            if "coverage_evidence" in r:
                r["coverage"] = {"requires_unknown_facts": True}
                r["coverage_evidence"] = [{"field": "requires_unknown_facts", "doc_id": "test", "quoted_span": "test"}]
    c = build_changes(b, hostile)
    assert c["T1"]["affected_address_ids"] == []
    jc = ids(b, lambda x: x["legal_city"] == "Jersey City, NJ")
    assert not set(c["T2"]["affected_address_ids"]) & set(jc)


def test_t5_mapping_exists_and_failed(data):
    _, rules, c = data
    m = map_test_rules(rules)
    assert m.get("MA-RENT-P1"), "MA-RENT-P1 has no mapped rule"
    by = {r["team_rule_id"]: r for r in rules}
    assert all(by[i]["status"] == "failed" for i in m["MA-RENT-P1"])
    assert all(i in c["T5"]["notes"] for i in m["MA-RENT-P1"])
    assert c["T5"]["affected_address_ids"] == []


def test_t1_to_t5_dataset_relative_properties(data):
    b, rules, changes = data
    assert change_property_errors(b, rules, changes) == []


def test_t1_to_t5_match_frozen_post_pr38_baseline(data):
    baseline = json.loads((Path(__file__).parents[1] / "fixtures" / "change_tests_baseline.json").read_text())
    changes = data[2]
    for tid in ("T1", "T2", "T3", "T4", "T5"):
        for field in ("affected_address_ids", "conflict_flag_address_ids"):
            ids = sorted(changes[tid].get(field, []))
            digest = hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()
            assert len(ids) == baseline[tid][field]["count"], (tid, field, len(ids))
            assert digest == baseline[tid][field]["sha256"], (tid, field, digest)


def test_t5_guard_targets_petition_25_21_only(data):
    b, rules, _ = data
    synthetic = {
        "team_rule_id": "r-test-future-cambridge-cap", "jurisdiction": "Cambridge, MA", "level": "city",
        "category": "rent_increase_limits", "status": "in_force", "title": "Synthetic later rent law",
        "requirement": "Synthetic rule used only to scope the T5 guard.", "effective_date": "2026-01-01",
        "coverage_conditions": None, "coverage": {}, "coverage_evidence": [], "event_only": False,
        "applies_only_in": None, "overrides": [], "interaction": None, "conflict_flag": False,
    }
    combined = [*copy.deepcopy(rules), synthetic]
    changes = build_changes(b, combined)
    assert changes["T5"]["affected_address_ids"] == []
    assert "petition 25-21" in changes["T5"]["notes"]
    assert_t5(b, combined, lookups(b, combined, "2026-10-01"))


def test_t5_guard_rejects_only_active_petition_25_21(data):
    b, rules, _ = data
    petition = set(map_test_rules(rules)["MA-RENT-P1"])
    hostile = copy.deepcopy(rules)
    for r in hostile:
        if r["team_rule_id"] in petition:
            r["status"] = "in_force"
            r["effective_date"] = "2026-01-01"
    with pytest.raises(SystemExit, match="petition 25-21"):
        assert_t5(b, hostile, lookups(b, hostile, "2026-10-01"))
