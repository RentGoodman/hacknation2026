from extraction.v3.dates import compute
from extraction.v3.verify import exact_or_normalized, snap

RAW = "Section 1.\nA landlord shall not  charge a deposit\nin excess of one month’s rent.\n"


def test_exact():
    assert exact_or_normalized(RAW, "shall not  charge") == ("shall not  charge", "exact")


def test_normalized_returns_raw_chars():
    got, how = exact_or_normalized(RAW, "deposit in excess of one month's rent.")
    assert how == "normalized" and got == "deposit\nin excess of one month’s rent." and got in RAW


def test_snap_and_reject():
    got, r = snap(RAW, "A landlord shall not charge any deposit in excess of one months rent")
    assert got and got in RAW and r >= 0.55
    assert snap(RAW, "completely unrelated sentence about parking garages")[0] is None


def test_date_formulas():
    f = {"kind": "first_day_of_nth_month_following", "n": 4, "anchor": "enactment", "anchor_date": "2026-01-15",
         "verbatim": "x"}
    assert compute(f) == "2026-05-01"
    assert compute({**f, "kind": "nth_month_after", "n": 12, "anchor_date": "2025-11-03"}) == "2026-11-01"
    assert compute({**f, "kind": "days_after", "n": 90, "anchor_date": "2026-01-01"}) == "2026-04-01"
    assert compute({**f, "anchor_date": None}) is None


def test_status_recomputed_from_dates():
    from extraction.v3.pipeline import recompute_status
    assert recompute_status({"status": "in_force", "effective_date": "2027-07-01"}) == "not_yet_effective"
    assert recompute_status({"status": "not_yet_effective", "effective_date": "2026-01-01"}) == "in_force"
    assert recompute_status({"status": "pending", "effective_date": None}) == "pending"


def test_bm25_finds_category_passages():
    from extraction.v3.bm25 import Index, probe_passages
    from extraction.v3.loader import load
    docs, _ = load()
    out = probe_passages(Index(docs), "MA", "security_deposits")
    assert "deposit" in out.lower()
