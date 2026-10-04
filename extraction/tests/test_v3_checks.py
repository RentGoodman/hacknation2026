from extraction.v3.checks import merge_findings, numbers_ok


def test_numbers_ok():
    rec = {"key_value": "1 month's rent; return within 30 days"}
    assert numbers_ok("Return within 30 days.", rec)
    assert not numbers_ok("Return within 14 days.", rec)


def test_merge_findings_flags_near_duplicates():
    a = {"jurisdiction": "CA", "category": "security_deposits", "status": "in_force", "title": "Deposit cap",
         "requirement": "Landlord may not demand a security deposit above one month of rent", "quoted_span": "x"}
    b = dict(a, title="Deposit cap (AB 12)")
    c = dict(a, category="security_deposits", title="Screening fee", requirement="application screening fee cap 60 dollars")
    out = merge_findings([a, b, c], {})
    assert any(f["kind"] == "unmerged_similar" and set(f["titles"]) == {"Deposit cap", "Deposit cap (AB 12)"} for f in out)
