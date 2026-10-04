from __future__ import annotations

from datetime import date, timedelta


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def compute(formula: dict | None) -> str | None:
    if not formula or not formula.get("anchor_date"):
        return None
    try:
        anchor = date.fromisoformat(formula["anchor_date"][:10])
    except ValueError:
        return None
    kind, n = formula.get("kind"), formula.get("n") or 0
    if kind in ("first_day_of_nth_month_following", "nth_month_after"):
        return _add_months(anchor, n).isoformat()
    if kind == "days_after":
        return (anchor + timedelta(days=n)).isoformat()
    if kind == "on_date":
        return anchor.isoformat()
    return None
