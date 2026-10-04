import json
from datetime import date
from types import SimpleNamespace

from engine.ingest_new import (CATEGORIES, build_entry, compute_affected, default_dates, extract_deterministic,
                               finalize, invalidated_no_rule_findings, parse_built, parse_coverage,
                               parse_effective, parse_units, span_is_verbatim, write_changes,
                               annotate_precedence)
from engine.verdict import lookups

TEXT = """NOTICE: FICTIONAL, for rehearsal.
CITY OF TESTVILLE
TESTVILLE TENANT PROTECTION ORDINANCE

Section 1.01 Applicability.
This chapter applies to every residential building in the City of Cambridge that contains five or more dwelling units. This chapter does not apply to owner-occupied buildings.

Section 1.02 Deposits.
A landlord shall return the security deposit within
10 days after the tenant vacates the unit.

Section 1.03 Findings.
The council must be thanked for its work on security deposit matters.

Section 1.04 Gardens.
A landlord shall water the garden every Friday morning without fail.

Section 1.05 Effective date.
This ordinance shall take effect on March 1, 2027.
"""

RENT_TEXT = """NOTICE: FICTIONAL, for rehearsal.
CITY OF CAMBRIDGE
CAMBRIDGE RENT LIMIT ORDINANCE

Section 2.01 Rent increase limit.
A landlord shall not increase the rent by more than three percent in any twelve-month period.

Section 2.02 Effective date.
This ordinance shall take effect on January 1, 2027.
"""

ALGORITHM_TEXT = """NOTICE: FICTIONAL, for rehearsal.
CITY OF CAMBRIDGE
CAMBRIDGE RENT-SETTING SOFTWARE ORDINANCE

Section 3.01 Algorithmic rent setting.
A landlord shall not use an algorithm or pricing software to coordinate or recommend residential rents.

Section 3.02 Effective date.
This ordinance shall take effect on January 1, 2027.
"""


def bld(aid, units, city="Cambridge, MA", state="MA"):
    return {"address_id": aid, "state": state, "legal_city": city, "legal_city_candidate": None,
            "city_status": "resolved", "city_confidence": 1.0, "units": units, "units_min": units,
            "units_max": units, "year_built": 1950, "co_date_min": "1950-01-01", "co_date_max": "1950-12-31",
            "threshold_year_case": False, "county": "Middlesex County", "unincorporated": False,
            "jurisdiction_mismatch": False}


def test_deterministic_extractor_and_verbatim_check():
    rules, rejected = extract_deterministic(TEXT, "Cambridge, MA")
    assert [r["category"] for r in rules] == ["security_deposits"]
    r = rules[0]
    assert r["quoted_span"] == "A landlord shall return the security deposit within 10 days after the tenant vacates the unit."
    assert span_is_verbatim(r["quoted_span"], TEXT)
    assert not span_is_verbatim("A landlord shall return the deposit within 30 days of the tenant leaving.", TEXT)
    assert r["coverage_conditions"]["min_units"] == 5 and r["category"] in CATEGORIES
    assert r["coverage_conditions"]["owner_conditions"].startswith("This chapter does not apply to owner-occupied")
    assert [x["heading"] for x in rejected] == ["Gardens"]


def test_fabricated_span_is_rejected(monkeypatch):
    import engine.ingest_new as m
    monkeypatch.setattr(m, "span_is_verbatim", lambda span, text: False)
    rules, rejected = m.extract_deterministic(TEXT, "Cambridge, MA")
    assert rules == [] and any("not found" in x["reason"] for x in rejected)


def test_unit_phrases():
    assert parse_units("buildings of six or more units") == (6, None)
    assert parse_units("containing 5 or more dwelling units") == (5, None)
    assert parse_units("at least ten rental units") == (10, None)
    assert parse_units("more than 3 units") == (4, None)
    assert parse_units("fewer than 5 units") == (None, 4)
    assert parse_units("no more than four dwelling units") == (None, 4)
    assert parse_units("two or fewer units") == (None, 2)
    assert parse_units("every building") == (None, None)


def test_built_phrases():
    assert parse_built("buildings built before 1980")[:2] == ("1979-12-31", None)
    assert parse_built("built on or before 1980")[:2] == ("1980-12-31", None)
    assert parse_built("constructed after 1995")[:2] == (None, "1995-12-31")
    assert parse_built("built in or after 1995")[:2] == (None, "1994-12-31")
    assert parse_built("built before June 1, 1979")[:2] == ("1979-05-31", None)
    assert parse_built("units with a certificate of occupancy issued before 1979")[3] == "certificate_of_occupancy"
    assert parse_built("buildings 15 years old or older")[2] == 15
    cov = parse_coverage("six or more units built before 1980", "Cambridge, MA")
    assert cov["min_units"] == 6 and cov["built_on_or_before"] == "1979-12-31"
    assert cov["construction_date_basis"] == "year_built"
    assert parse_coverage("every building", "Cambridge, MA") is None


def test_effective_date_parsing():
    assert parse_effective("This ordinance shall take effect on January 1, 2027.") == "2027-01-01"
    assert parse_effective("The ordinance becomes effective on March 15th, 2027 and applies to leases") == "2027-03-15"
    assert parse_effective("effective on 2027-07-01") == "2027-07-01"
    assert parse_effective("Effective January 1, 2027, landlords shall") == "2027-01-01"
    assert parse_effective("No date here.") is None
    rules, _ = extract_deterministic(TEXT, "Cambridge, MA")
    new = finalize(rules, TEXT, "Cambridge, MA", None, "f.txt")
    assert new[0]["effective_date"] == "2027-03-01" and new[0]["status"] == "not_yet_effective"
    assert new[0]["team_rule_id"] == "h16-0001" and new[0]["source_doc_id"] == "HOUR16"
    new = finalize(rules, TEXT, "Cambridge, MA", "2026-01-01", "f.txt")
    assert new[0]["status"] == "in_force"


def test_default_dates():
    assert default_dates("2027-01-01", None, None) == ("2026-12-31", "2027-01-01")
    assert default_dates("2027-01-01", "2026-12-01", "2027-02-01") == ("2026-12-01", "2027-02-01")


def test_t6_cambridge_rent_cap_flags_c40p_conflict_and_invalidates_no_rule():
    buildings = {"A1": bld("A1", 8), "A2": bld("A2", 4, city="Boston, MA")}
    bar = {
        "team_rule_id": "ma-c40p", "jurisdiction": "MA", "level": "state",
        "category": "rent_increase_limits", "status": "in_force",
        "title": "Statewide prohibition on local rent control", "requirement": "Cities may not enact rent control.",
        "key_value": None, "coverage_conditions": None, "exemptions": None, "overrides": [],
        "interaction": None, "effective_date": None, "citation": "G.L. c. 40P, § 4",
        "source_doc_id": "D048", "source_url": "https://example.test/D048",
        "quoted_span": "No city or town may enact, maintain or enforce rent control of any kind",
        "confidence": 1.0, "conflict_flag": False,
    }
    rules, rejected = extract_deterministic(RENT_TEXT, "Cambridge, MA")
    assert not rejected and [r["category"] for r in rules] == ["rent_increase_limits"]
    new = finalize(rules, RENT_TEXT, "Cambridge, MA", None, "rent.txt")
    combined = annotate_precedence([bar] + new)
    res = compute_affected(buildings, combined[:1], combined[1:], *default_dates("2027-01-01", None, None))
    assert res["affected"] == ["A1"]
    assert res["conflicts"] == ["A1"]
    findings = [{"jurisdiction": "Cambridge, MA", "category": "rent_increase_limits",
                 "citation": "G.L. c. 40P, § 4", "source_doc_id": "D048", "quoted_span": "proved"}]
    assert invalidated_no_rule_findings(new, findings) == [{
        "jurisdiction": "Cambridge, MA", "category": "rent_increase_limits",
        "citation": "G.L. c. 40P, § 4", "source_doc_id": "D048",
    }]


def test_t6_algorithmic_rule_transitions_on_effective_day():
    buildings = {"A1": bld("A1", 8), "A2": bld("A2", 8, city="Boston, MA")}
    rules, rejected = extract_deterministic(ALGORITHM_TEXT, "Cambridge, MA")
    assert not rejected and [r["category"] for r in rules] == ["algorithmic_rent_setting"]
    new = finalize(rules, ALGORITHM_TEXT, "Cambridge, MA", None, "algorithm.txt")
    before, after = default_dates("2027-01-01", None, None)
    res = compute_affected(buildings, [], new, before, after)
    assert (before, after) == ("2026-12-31", "2027-01-01")
    assert res["pairs"]["A1"]["h16-0001"] == ["not_yet_effective", "applies"]
    assert res["affected"] == ["A1"]


def test_affected_on_synthetic_buildings(tmp_path):
    buildings = {"A1": bld("A1", 8), "A2": bld("A2", 4), "A3": bld("A3", 12, city="Boston, MA"),
                 "A4": bld("A4", None)}
    buildings["A4"].update(units_min=None, units_max=None)
    rules, _ = extract_deterministic(TEXT, "Cambridge, MA")
    new = finalize(rules, TEXT, "Cambridge, MA", "2027-03-01", "f.txt")
    before, after = default_dates("2027-03-01", None, None)
    before_lookups = lookups(buildings, new, before)
    assert not before_lookups["A2"]
    assert {e["result"] for e in before_lookups["A1"] + before_lookups["A4"]} == {"not_yet_effective"}
    res = compute_affected(buildings, [], new, before, after)
    assert res["applies"] == ["A1"]
    assert res["unknown"] == ["A4"]
    assert res["affected"] == ["A1", "A4"]
    assert res["pairs"]["A1"]["h16-0001"] == ["not_yet_effective", "applies"]
    entry, by_city = build_entry(res, buildings, new, "Cambridge, MA", "2027-03-01", "deterministic", [])
    assert by_city == {"Cambridge, MA": 2} and "Unknown, listed separately: A4" in entry["notes"]
    assert entry["conflict_flag_address_ids"] == []
    assert compute_affected(buildings, [], new, "2027-01-01", "2027-02-01")["affected"] == []


def test_write_changes_keeps_other_entries_byte_identical(tmp_path):
    p = tmp_path / "changes.json"
    base = {"_meta": {"a": 1}, "T1": {"affected_address_ids": ["A1"], "notes": "x"}}
    p.write_text(json.dumps(base, indent=2) + "\n")
    write_changes(p, {"affected_address_ids": [], "notes": "n"})
    first = p.read_text()
    assert json.loads(first)["T1"] == base["T1"] and list(json.loads(first)) == ["_meta", "T1", "T6"]
    write_changes(p, {"affected_address_ids": ["A2"], "notes": "n2"})
    assert json.loads(p.read_text())["T6"]["affected_address_ids"] == ["A2"]
    assert p.read_text().startswith(first[: first.index('"T6"')])


def test_recompute_entry_matches_ingest(tmp_path):
    import json
    from engine.ingest_new import recompute_entry
    buildings = {"A1": bld("A1", 8), "A2": bld("A2", 4)}
    rules, _ = extract_deterministic(TEXT, "Cambridge, MA")
    new = finalize(rules, TEXT, "Cambridge, MA", "2027-03-01", "f.txt")
    p = tmp_path / "rules_hour16.json"
    p.write_text(json.dumps({"jurisdiction": "Cambridge, MA", "effective_date": "2027-03-01",
                             "extractor": "deterministic", "rejected": [], "rules": new}))
    res = compute_affected(buildings, [], new, *default_dates("2027-03-01", None, None))
    entry, _ = build_entry(res, buildings, new, "Cambridge, MA", "2027-03-01", "deterministic", [])
    assert recompute_entry(buildings, [], p) == entry and entry["affected_address_ids"] == ["A1"]


def test_dry_run_does_not_leave_rules_file(monkeypatch, tmp_path):
    import engine.ingest_new as m
    import engine.run as engine_run

    source = tmp_path / "ordinance.txt"
    source.write_text(ALGORITHM_TEXT)
    rules_out = tmp_path / "rules_hour16.json"
    monkeypatch.setattr(engine_run, "evaluation_rules", lambda fetch=False: [])
    monkeypatch.setattr(m, "load_buildings", lambda: {"A1": bld("A1", 8)})
    monkeypatch.setattr(m, "load_no_rule_findings", lambda: [])
    args = SimpleNamespace(
        file=str(source), jurisdiction="Cambridge, MA", effective=None,
        as_of_before=None, as_of_after=None, rules_out=str(rules_out), rules_out_abs=True,
        changes=str(tmp_path / "changes.json"), test_id="T6", extractor="deterministic",
        summary_out=None, dry_run=True,
    )
    entry, summary = m.run(args)
    assert entry["affected_address_ids"] == ["A1"]
    assert summary["rules_out"] is None
    assert not rules_out.exists()
