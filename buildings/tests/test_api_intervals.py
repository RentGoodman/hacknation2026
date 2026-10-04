from buildings import api

AS_OF = "2026-10-01"


def building(**overrides):
    record = {
        "year_built": None,
        "year_built_max": 1985,
        "co_date_min": None,
        "co_date_max": "1985-12-31",
        "co_date_method": "SANDAG APN upper bound",
        "year_built_max_method": "SANDAG APN",
        "units": None,
        "units_min": None,
        "units_max": None,
        "units_method": "not in public record",
        "use_code": None,
        "use_description": None,
    }
    return {**record, **overrides}


def test_sandag_upper_bound_resolves_only_conclusive_age_checks():
    assert api.check_record(building(), "year_built", ">", "as_of-15y", as_of=AS_OF) == "false"
    assert api.check_record(building(), "year_built", ">", {"as_of_minus_years": 15}, as_of=AS_OF) == "false"
    assert api.check_record(building(year_built_max=2025), "year_built", ">", "as_of-15y",
                            as_of=AS_OF) == "unknown"
    assert api.check_record(building(year_built_max=None), "year_built", ">", "as_of-15y") == "unknown"
    assert api.check_record(building(), "certificate_of_occupancy_date", ">", "as_of-15y",
                            as_of=AS_OF) == "false"


def test_one_sided_co_interval_uses_upper_bound_without_inventing_lower_bound():
    record = building(co_date_max="1979-12-31")
    assert api.check_record(record, "certificate_of_occupancy_date", "<=", "1980-01-01") == "true"
    assert api.check_record(record, "certificate_of_occupancy_date", ">", "1980-01-01") == "false"
    assert api.check_record(record, "certificate_of_occupancy_date", "<=", "1979-06-13") == "unknown"


def test_unit_intervals_are_three_valued():
    record = building(units_min=4, units_max=8)
    assert api.check_record(record, "units", "<=", 4) == "unknown"
    assert api.check_record(record, "units", ">=", 5) == "unknown"
    assert api.check_record(record, "units", "<=", 10) == "true"
    assert api.check_record(record, "units", "in", [1, 2]) == "false"
    assert api.check_record(building(units_min=2, units_max=4), "units", "in", [2, 3, 4]) == "true"


def test_fact_exposes_bounds_and_provenance():
    co = api.fact_record(building(), "certificate_of_occupancy_date")
    assert co["known"] is False and (co["lower"], co["upper"]) == (None, "1985-12-31")
    assert "SANDAG" in co["method"] and co["reason"] == "bounded_by_public_record"
    year = api.fact_record(building(), "year_built")
    assert (year["lower"], year["upper"]) == (None, 1985)
    assert year["reason"] == "upper_bound_from_public_record"


def test_text_facts_are_true_or_unknown_never_assumed_false():
    plain = building(use_description="Five or more apartments")
    for name in ("subsidized", "elderly_housing", "tenancy_in_common"):
        assert api.fact_record(plain, name)["value"] is None
    assert api.fact_record(building(use_description="SUBSD HOUSING S- 8"), "subsidized")["value"] is True
    assert api.fact_record(building(use_description="ELDERLY HOME"), "elderly_housing")["value"] is True
    assert api.fact_record(building(use_code="TIC"), "tenancy_in_common")["value"] is True
