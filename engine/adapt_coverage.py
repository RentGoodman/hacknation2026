PART1_KEYS = {"summary", "construction_date_basis", "built_on_or_before", "built_after", "min_building_age_years",
              "min_units", "max_units", "owner_conditions", "other_conditions"}


def is_part1(cov):
    return isinstance(cov, dict) and bool(PART1_KEYS & set(cov)) and not ({"all", "any"} & set(cov))


def _built(b, op, cutoff, basis):
    from .verdict import _co_date, _year_built_date
    if basis == "certificate_of_occupancy":
        return _co_date(b, op, cutoff)
    return _year_built_date(b, op, cutoff)


def evaluate(b, cov, as_of):
    from .verdict import _units
    checks = []
    basis = cov.get("construction_date_basis")
    if cov.get("built_on_or_before"):
        checks.append(_built(b, "<=", cov["built_on_or_before"], basis))
    if cov.get("built_after"):
        checks.append(_built(b, ">", cov["built_after"], basis))
    if cov.get("min_building_age_years") is not None:
        n = cov["min_building_age_years"]
        try:
            cutoff = as_of.replace(year=as_of.year - n)
        except ValueError:
            cutoff = as_of.replace(year=as_of.year - n, day=28)
        checks.append(_built(b, "<=", cutoff.isoformat(), "year_built"))
    if cov.get("min_units") is not None:
        checks.append(_units(b, ">=", cov["min_units"]))
    if cov.get("max_units") is not None:
        checks.append(_units(b, "<=", cov["max_units"]))
    notes = [f"Not verifiable from the data: {cov[k].strip()}" for k in ("owner_conditions", "other_conditions")
             if isinstance(cov.get(k), str) and cov[k].strip()]
    vals = [v for v, _ in checks]
    if False in vals:
        return False, None, notes
    if None in vals:
        return None, "; ".join(w for v, w in checks if v is None and w), notes
    return True, None, notes
