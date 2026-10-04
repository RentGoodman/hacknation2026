import copy
import json
from pathlib import Path

from extraction.v3.ids import assign, fill_overrides

OLD = json.loads((Path(__file__).resolve().parents[2] / "out" / "rules.json").read_text())["rules"]


def test_ids_stable_for_same_laws():
    new = copy.deepcopy(OLD)
    assign(new, OLD)
    ids = {r["team_rule_id"] for r in new}
    assert len(ids) == len(new)
    assert ids <= {r["team_rule_id"] for r in OLD}


def test_canonical_ids_unique_and_change_tests_aligned():
    new = copy.deepcopy(OLD)
    assign(new, OLD)
    cids = [r["canonical_id"] for r in new]
    assert len(set(cids)) == len(cids)
    for t in ["MA-ALG-P1", "MA-ALG-P2", "NJ-ALG-01"]:
        assert t in cids


def test_new_law_gets_new_id():
    r = {"jurisdiction": "Newark, NJ", "category": "rent_increase_limits", "status": "in_force",
         "citation": "Newark Mun. Code § 19:2-1", "title": "x"}
    rules = [r]
    assign(rules, OLD)
    assert r["team_rule_id"] not in {o["team_rule_id"] for o in OLD} and r["canonical_id"] == "NWK-RENT-01"


def test_overrides_from_coverage_flags():
    s = {"team_rule_id": "r-1", "jurisdiction": "CA", "category": "rent_increase_limits", "citation": "A",
         "coverage": {"yields_to_local_rule": True}, "conflict_flag": False}
    c = {"team_rule_id": "r-2", "jurisdiction": "Los Angeles, CA", "category": "rent_increase_limits",
         "citation": "B", "coverage": {}, "conflict_flag": False}
    fill_overrides([s, c])
    assert s["overrides"] == ["r-2"] and c["overrides"] == ["r-1"] and "Yields" in s["interaction"]
