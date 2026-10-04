import json

from engine.rules import load_buildings
from engine.run import build_outputs, evaluation_rules
from engine.verdict import lookups

DATES = ["2025-12-31", "2026-01-02", "2026-10-01", "2027-07-02"]


def _dump(as_of):
    return json.dumps(lookups(load_buildings(), evaluation_rules(), as_of), sort_keys=True)


def test_lookups_identical_across_runs():
    for d in DATES:
        assert _dump(d) == _dump(d), d


def test_build_outputs_identical_across_runs():
    a, _ = build_outputs("2026-10-01", fetch=False)
    b, _ = build_outputs("2026-10-01", fetch=False)
    assert a == b


def test_evaluation_rules_match_engine_run():
    _, s = build_outputs("2026-10-01", fetch=False)
    assert _dump("2026-10-01") == json.dumps(s["L"], sort_keys=True)
