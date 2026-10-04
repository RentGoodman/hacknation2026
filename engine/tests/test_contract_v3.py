from engine.verdict import verdicts_for_building

AS_OF = "2026-10-01"
NO_LINKS = {"supersedes": set(), "uncertain": set(), "conflicts": set()}


def bldg(state="CA", city="Los Angeles, CA", year=1950, units=10, units_min=None, units_max=None):
    return {"state": state, "legal_city": city, "city_status": "resolved", "legal_city_candidate": None,
            "year_built": year, "units": units, "units_min": units_min, "units_max": units_max,
            "property_type": "multifamily_5plus", "threshold_year_case": False}


def rule(rid="r-v3", **kw):
    r = {"team_rule_id": rid, "title": "Test rule", "level": "state", "jurisdiction": "CA",
         "category": "notice_requirements", "status": "in_force", "effective_date": "2020-01-01",
         "coverage_conditions": None}
    r.update(kw)
    return r


def ev(*fields):
    return [{"field": f, "doc_id": "d1", "quoted_span": f"text for {f}"} for f in fields]


def one(b, r, as_of=AS_OF):
    out = {e["team_rule_id"]: e for e in verdicts_for_building(b, [r], as_of, links=NO_LINKS)}
    return out.get(r["team_rule_id"])


def test_absent_fields_unchanged():
    assert one(bldg(), rule())["result"] == "applies"


def test_event_only_remains_in_submission_lookups():
    entry = one(bldg(), rule(event_only=True))
    assert entry is not None and entry["result"] == "applies"
    assert one(bldg(), rule(event_only=False))["result"] == "applies"


def test_applies_only_in():
    r = rule(applies_only_in="Los Angeles, CA")
    assert one(bldg(), r)["result"] == "applies"
    assert one(bldg(city="San Diego, CA"), r) is None
    assert one(bldg(), rule(applies_only_in=None))["result"] == "applies"


def test_units_need_evidence():
    r = rule(coverage={"min_units": 20})
    assert one(bldg(units=10), r)["result"] == "applies"
    r["coverage_evidence"] = ev("min_units")
    assert one(bldg(units=10), r) is None
    assert one(bldg(units=25), r)["result"] == "applies"
    assert one(bldg(units=None, units_min=10, units_max=30), r)["result"] == "unknown"


def test_v3_coverage_takes_precedence_over_legacy():
    r = rule(coverage_conditions={"all": [{"fact": "units", "op": ">=", "value": 100}]},
             coverage={"max_units": 50}, coverage_evidence=ev("max_units"))
    assert one(bldg(units=10), r)["result"] == "applies"


def test_construction_cutoff():
    cc = {"basis": "certificate_of_occupancy", "covered_if": "on_or_before", "date": "1978-10-01"}
    r = rule(coverage={"construction_cutoff": cc}, coverage_evidence=ev("construction_cutoff"))
    assert one(bldg(year=1950), r)["result"] == "applies"
    assert one(bldg(year=1990), r) is None
    assert one(bldg(year=1978), r)["result"] == "unknown"
    r2 = rule(coverage={"construction_cutoff": {"basis": "year_built", "covered_if": "after", "date": "2000-12-31"}},
              coverage_evidence=ev("construction_cutoff.date"))
    assert one(bldg(year=2005), r2)["result"] == "applies"
    assert one(bldg(year=1990), r2) is None


def test_owner_occupied_exemption():
    r = rule(coverage={"owner_occupied_exemption_max_units": 4},
             coverage_evidence=ev("owner_occupied_exemption_max_units"))
    assert one(bldg(units=10), r)["result"] == "applies"
    assert one(bldg(units=2), r)["result"] == "unknown"


def test_new_construction_exemption():
    nc = {"years": 15, "basis": "certificate_of_occupancy", "requires_owner_filing": False}
    r = rule(coverage={"new_construction_exemption": nc}, coverage_evidence=ev("new_construction_exemption"))
    assert one(bldg(year=1950), r)["result"] == "applies"
    assert one(bldg(year=2020), r) is None
    assert one(bldg(year=2011), r)["result"] == "unknown"
    nc2 = dict(nc, requires_owner_filing=True)
    r2 = rule(coverage={"new_construction_exemption": nc2}, coverage_evidence=ev("new_construction_exemption"))
    assert one(bldg(year=2020), r2)["result"] == "unknown"


def test_requires_unknown_facts_and_notes():
    r = rule(coverage={"requires_unknown_facts": ["tenancy_start"], "unverifiable_exemptions": ["seasonal units"]},
             coverage_evidence=ev("requires_unknown_facts", "unverifiable_exemptions"))
    e = one(bldg(), r)
    assert e["result"] == "unknown" and "seasonal units" in e["explanation"]


def test_evidenced_general_scope_does_not_fall_back_to_legacy_prose():
    r = rule(
        coverage={"requires_unknown_facts": False, "unverifiable_exemptions": ["owner roommate"]},
        coverage_evidence=ev("requires_unknown_facts", "unverifiable_exemptions"),
        coverage_conditions={"summary": "owner occupancy cannot be verified"},
        verification={"verdicts": {"coverage": "supported"}},
    )
    e = one(bldg(), r)
    assert e["result"] == "applies"
    assert "owner roommate" in e["explanation"]


def test_date_audit():
    r = rule(effective_date="2027-01-01", in_force_since="2020-01-01", current_version_effective="2027-01-01",
             requirement_is_new=False, prior_version_note="Prior cap was 10%.")
    assert one(bldg(), r, "2027-02-01")["result"] == "applies"
    e = one(bldg(), r, "2026-10-01")
    assert e["result"] == "applies" and "Earlier version in force since 2020-01-01" in e["explanation"]
    assert one(bldg(), r, "2019-06-01")["result"] == "not_yet_effective"
    r2 = rule(effective_date="2025-01-01", current_version_effective="2027-01-01")
    assert one(bldg(), r2, "2024-06-01")["result"] == "not_yet_effective"
    assert "earlier version" in one(bldg(), r2, "2026-01-01")["explanation"]
