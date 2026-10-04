from buildings.enrich import full_year
from buildings.facts import explicit_units, units_interval, zip_suspect
from buildings.resolve import request_fields

NJ = "NJOGIS Parcels & MOD-IV Composite"


def row(desc, units="", code="4C", source=NJ):
    return {
        "units": units,
        "use_description": desc,
        "source_dataset": source,
        "use_code": code,
    }


def test_mod_iv_unattached_garage_is_not_dwelling_units():
    assert explicit_units("3SF5UG", NJ) == (None, None)
    assert explicit_units("USCB16UG", NJ) == (None, None)
    got = units_interval(row("USCB16UG"))
    assert got["units"] is None
    assert (got["units_min"], got["units_max"]) == (5, None)
    assert got["units_method"].startswith("class: NJ MOD-IV")


def test_mod_iv_bare_u_is_still_a_dwelling_unit_count():
    assert explicit_units("4S-B-A-17U", NJ) == (17, "4S-B-A-17U")
    assert explicit_units("5B-1OU", NJ) == (10, "5B-1OU")


def test_csv_unit_count_conflicting_with_upper_bound_becomes_interval():
    got = units_interval(row("TIC Bldg 4 units or less", units="5", code="TIC",
                             source="DataSF wv5m-vpq2 (2025 roll)"))
    assert got["units"] is None and got["units_raw"] == 5 and got["units_conflict"] is True
    assert (got["units_min"], got["units_max"]) == (None, 5)
    assert "widened" in got["units_method"]


def test_conflicting_exact_counts_keep_both_values_possible():
    got = units_interval(row("13B-93U-2C-G", units="2"))
    assert got["units"] is None and got["units_conflict"] is True
    assert (got["units_min"], got["units_max"]) == (2, 93)


def test_conflicting_csv_above_range_widens_upper_bound():
    got = units_interval(row("Apartment 5 to 14 Units", units="15", code="A/125",
                             source="Boston Property Assessment FY2026"))
    assert got["units"] is None and got["units_conflict"] is True
    assert (got["units_min"], got["units_max"]) == (5, 15)


def test_mod_iv_owner_mailing_zip_is_never_sent_as_situs_zip():
    assert zip_suspect("NJ", "07105", NJ) is True
    rec = {"street_address": "76-80 BRUEN ST", "postal_city": "Newark", "state": "NJ",
           "zip": "07105", "source_dataset": NJ}
    assert request_fields(rec) == ("76 BRUEN ST", "Newark", "NJ", "")
    assert zip_suspect("MA", "02124", "Boston Property Assessment FY2026") is False


def test_sandag_year_rejects_zero_invalid_and_future_values():
    assert full_year("85") == 1985
    assert full_year(7) == 2007
    assert full_year("1985") == 1985
    assert all(full_year(value) is None for value in (None, "", "0", "00", "no", "2027"))
