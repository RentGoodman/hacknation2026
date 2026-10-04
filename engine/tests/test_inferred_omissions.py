from scripts.audit_inferred_omissions import audit

import json
import re
from pathlib import Path


def test_no_current_omission_depends_on_an_inferred_fact():
    report = audit()
    assert report["coverage_omissions_checked"] == 92
    assert report["counts"] == {"pairs": 0, "addresses": 0, "by_fact": {}}
    assert report["inferred_fact_omissions"] == []


def test_published_explanations_are_short_and_detail_keeps_reasoning():
    root = Path(__file__).resolve().parents[2]
    lookups = json.loads((root / "out" / "lookups.json").read_text())["lookups"]
    detail = json.loads((root / "out" / "lookups_detail.json").read_text())["addresses"]
    for address_id, entries in lookups.items():
        for entry in entries:
            explanation = entry["explanation"]
            assert 15 <= len(explanation.split()) <= 25
            assert re.search(r"\br-\d{4}\b", explanation) is None
            record = detail[address_id]["rules"][entry["team_rule_id"]]
            assert explanation == record["summary"]
            assert record["reasoning"]
