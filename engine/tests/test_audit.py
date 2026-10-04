import copy
import json
from pathlib import Path

import pytest

from engine.audit import check_lookups, fresh_lookups
from engine.rules import load_buildings, load_rules

AS_OF = "2026-10-01"


@pytest.fixture(scope="module")
def data():
    buildings = load_buildings()
    rules, _, _ = load_rules(fetch=False)
    return buildings, rules, fresh_lookups(buildings, AS_OF)


def first(L, pred):
    return next((aid, e) for aid, entries in L.items() for e in entries if pred(e))


def test_engine_output_has_no_violations(data):
    buildings, rules, L = data
    bad, _ = check_lookups(L, buildings, rules, AS_OF)
    assert bad == []


def test_compact_published_output_uses_detail_for_precedence_audit(data):
    buildings, rules, _ = data
    root = Path(__file__).resolve().parents[2]
    published = json.loads((root / "out" / "lookups.json").read_text())
    detail = json.loads((root / "out" / "lookups_detail.json").read_text())["addresses"]
    bad, _ = check_lookups(published["lookups"], buildings, rules, published["as_of"], detail=detail)
    assert bad == []


@pytest.mark.parametrize("break_it, expect", [
    ("wrong_state", "reported in"),
    ("failed_rule", "failed rule was reported"),
    ("fake_pending", "does not match status"),
    ("future_in_force", "before its effective date"),
    ("bare_superseded", "without naming"),
    ("bad_result", "result is not one of"),
    ("missing_address", "addresses:"),
])
def test_audit_catches(data, break_it, expect):
    buildings, rules, L = data
    L, rules = copy.deepcopy(L), copy.deepcopy(rules)
    by_id = {r["team_rule_id"]: r for r in rules}
    aid, e = first(L, lambda e: e["result"] == "applies")
    rule = by_id[e["team_rule_id"]]
    if break_it == "wrong_state":
        other = next(a for a, b in buildings.items() if b["state"] != buildings[aid]["state"])
        L[other].append(dict(e))
    elif break_it == "failed_rule":
        rule["status"] = "failed"
    elif break_it == "fake_pending":
        e["result"] = "pending"
    elif break_it == "future_in_force":
        rule["effective_date"] = "2099-01-01"
    elif break_it == "bare_superseded":
        e["result"], e["explanation"] = "superseded", "Covered, but another rule governs."
    elif break_it == "bad_result":
        e["result"] = "maybe"
    elif break_it == "missing_address":
        del L[aid]
    bad, _ = check_lookups(L, buildings, rules, AS_OF)
    assert any(expect in line for line in bad), bad[:5]
