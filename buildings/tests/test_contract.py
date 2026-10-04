import pytest

from buildings import api


def test_500_ids_in_csv_order():
    ids = api.all_ids()
    assert len(ids) == 500 and len(set(ids)) == 500
    assert ids == [f"A{i:04d}" for i in range(1, 501)]


def test_unknown_id_raises():
    with pytest.raises(KeyError):
        api.get_building("A9999")


def test_a0016_san_francisco_confirmed():
    j = api.jurisdictions("A0016")
    assert j["city"] == "San Francisco, CA" and j["city_confidence"] == "confirmed"


def test_a0065_dorchester_is_boston():
    assert api.get_building("A0065")["postal_city"] == "Dorchester"
    j = api.jurisdictions("A0065")
    assert j["city"] == "Boston, MA" and j["city_confidence"] == "confirmed"
    assert api.matches_jurisdiction("A0065", "Boston, MA", "city") == "yes"
    assert api.matches_jurisdiction("A0065", "MA", "state") == "yes"


def test_a0279_resolved_by_mod_iv_municipality():
    j = api.jurisdictions("A0279")
    assert j["city"] == "Jersey City, NJ" and j["city_status"] == "resolved_by_mod_iv_municipality"
    assert j["city_confidence"] == "confirmed" and j["city_confidence_score"] == 0.9
    assert api.matches_jurisdiction("A0279", "Jersey City, NJ", "city") == "yes"
    assert api.matches_jurisdiction("A0279", "Hoboken, NJ", "city") == "no"


def test_no_postal_only_left():
    statuses = {api.get_building(i)["city_status"] for i in api.all_ids()}
    assert "postal_only" not in statuses
    for i in ("A0352", "A0400", "A0428"):
        assert api.jurisdictions(i)["city"] == "Newark, NJ"
    b = api.get_building("A0346")
    assert b["city_status"] == "postal_fallback" and b["city_confidence"] == 0.8 and "postal_fallback" in b["flags"]


def _ids_with_status(status):
    return [i for i in api.all_ids() if api.get_building(i)["city_status"] == status]


def test_mod_iv_municipality_is_confirmed():
    ids = _ids_with_status("resolved_by_mod_iv_municipality")
    assert ids == ["A0279", "A0352", "A0400", "A0428"]
    for i in ids:
        j = api.jurisdictions(i)
        assert j["city_confidence"] == "confirmed" and j["city"] == api.get_building(i)["legal_city"]
        assert j["city_candidate"] is None
        assert api.matches_jurisdiction(i, j["city"], "city") == "yes"
        assert api.matches_jurisdiction(i, "Hoboken, NJ", "city") == "no"


def test_postal_fallback_is_candidate():
    ids = _ids_with_status("postal_fallback")
    assert ids == ["A0346"]
    j = api.jurisdictions("A0346")
    assert j["city"] is None and j["city_confidence"] == "candidate" and j["city_candidate"] == "San Diego, CA"
    assert api.matches_jurisdiction("A0346", "San Diego, CA", "city") == "unknown"
    assert api.matches_jurisdiction("A0346", "Los Angeles, CA", "city") == "no"
    assert api.matches_jurisdiction("A0346", "CA", "state") == "yes"


def test_a0346_without_house_number_is_not_promoted_to_confirmed_city():
    b = api.get_building("A0346")
    assert b["input_address"].startswith("AUBURN DR,")
    assert b["city_status"] == "postal_fallback"
    assert api.jurisdictions("A0346")["city_confidence"] == "candidate"


def test_unmapped_city_status_raises():
    with pytest.raises(ValueError):
        api.check_statuses({"X": {"city_status": "postal_guess"}})
    with pytest.raises(ValueError):
        api.jurisdictions_record({"state": "CA", "city_status": "postal_guess"})
    api.check_statuses({i: api.get_building(i) for i in api.all_ids()})


def test_unit_intervals_have_provenance():
    for i in api.all_ids():
        b = api.get_building(i)
        assert b["units_method"]
        if b["units"] is None:
            assert b["units_min"] is not None or b["units_max"] is not None, i
    b = api.get_building("A0227")
    assert b["units"] is None and b["units_raw"] == 2
    assert (b["units_min"], b["units_max"]) == (2, 93) and "units_conflict" in b["flags"]


def test_a0398_conflicting_unit_sources_do_not_decide_thresholds():
    b = api.get_building("A0398")
    assert (b["units_min"], b["units_max"]) == (None, 5)
    assert api.check("A0398", "units", ">=", 5) == "unknown"
    assert api.check("A0398", "units", "<=", 4) == "unknown"

def test_a0005_units_lower_bound():
    f = api.fact("A0005", "units")
    assert f["known"] is False and f["lower_bound"] == 5
    assert api.check("A0005", "units", ">=", 5) == "true"
    assert api.check("A0005", "units", "<", 5) == "false"
    assert api.check("A0005", "units", ">=", 10) == "unknown"


def test_a0107_certificate_cutoff_unknown():
    assert api.check("A0107", "certificate_of_occupancy_date", "<=", "1978-10-01") == "unknown"


def test_certificate_cutoff_outside_year():
    assert api.check("A0016", "certificate_of_occupancy_date", "<=", "1979-06-13") == "true"


def test_berkeley_year_built_unknown():
    berkeley = [i for i in api.all_ids() if api.jurisdictions(i)["city"] == "Berkeley, CA"]
    assert len(berkeley) == 40
    for i in berkeley:
        assert api.check(i, "year_built", "<", 1980) == "unknown"


@pytest.mark.parametrize("name", ["owner_type", "tenancy_start"])
def test_not_in_source_facts(name):
    assert api.fact("A0001", name) == {"value": None, "known": False, "lower_bound": None, "reason": "not_in_source"}


def test_certificate_of_occupancy_fact_exposes_interval():
    fact = api.fact("A0016", "certificate_of_occupancy_date")
    assert fact["known"] is False and fact["value"] is None
    assert (fact["lower"], fact["upper"]) == ("1926-01-01", "1926-12-31")
    assert fact["method"].startswith("year_built proxy")


def test_matches_jurisdiction_normalizes():
    assert api.matches_jurisdiction("A0016", "san francisco, ca", "city") == "yes"
    assert api.matches_jurisdiction("A0016", "ca", "state") == "yes"


def test_output_matches_schema():
    import json
    from pathlib import Path

    import jsonschema
    schema = json.loads((Path(api.__file__).parent / "schema" / "buildings.schema.json").read_text())
    jsonschema.validate({i: api.get_building(i) for i in api.all_ids()}, schema)


def test_unresolved_city_is_unknown_not_no():
    b = dict(api.get_building("A0065"), city_status="not_geocoded", legal_city=None, legal_city_candidate=None)
    assert api.matches_jurisdiction_record(b, "Boston, MA", "city") == "unknown"
    assert api.matches_jurisdiction_record(b, "Jersey City, NJ", "city") == "no"
    b["city_status"] = "no_place"
    assert api.matches_jurisdiction_record(b, "Cambridge, MA", "city") == "unknown"


def test_co_date_year_known():
    b = api.get_building("A0016")
    assert (b["co_date_min"], b["co_date_max"]) == ("1926-01-01", "1926-12-31")
    assert b["co_date_method"].startswith("year_built proxy")
    assert "certificate_of_occupancy_date" not in b["missing_facts"]


def test_co_date_year_absent():
    for i in api.all_ids():
        b = api.get_building(i)
        if b["year_built"] is None:
            assert b["co_date_min"] is None and "certificate_of_occupancy_date" in b["missing_facts"], i
            if b["source_dataset"].startswith("Alameda"):
                assert b["co_date_max"] is None and b["year_built_max"] is None, i


def test_co_date_threshold_year_stays_unknown():
    thr = [i for i in api.all_ids() if api.get_building(i)["threshold_year_case"]]
    assert thr
    for i in thr:
        b = api.get_building(i)
        assert b["co_date_min"][:4] == b["co_date_max"][:4] == str(b["year_built"])
    assert api.check("A0107", "certificate_of_occupancy_date", "<=", "1978-10-01") == "unknown"


def test_sandag_upper_bound_has_provenance():
    sd = [api.get_building(i) for i in api.all_ids() if api.get_building(i)["source_dataset"] == "SANDAG/SanGIS parcels"]
    enriched = [b for b in sd if b["year_built_max"] is not None]
    assert len(enriched) >= 40
    for b in enriched:
        assert b["year_built"] is None and b["co_date_min"] is None
        assert b["co_date_max"] == f"{b['year_built_max']}-12-31"
        assert "APN" in b["year_built_max_method"] and "SANDAG" in b["co_date_method"]


def test_text_facts_never_false():
    seen = set()
    for i in api.all_ids():
        b = api.get_building(i)
        for k in ("subsidized", "elderly_housing", "tenancy_in_common"):
            assert b[k] in (True, None)
            assert (b[k] is True) == (b[k + "_source"] is not None)
            if b[k]:
                seen.add(k)
    assert seen == {"subsidized", "elderly_housing", "tenancy_in_common"}


def test_new_use_codes_mapped():
    types = {(api.get_building(i)["use_code"], api.get_building(i)["property_type"]) for i in api.all_ids()}
    assert ("A/125", "multifamily_5plus") in types and ("A/118", "other") in types and ("TIC", "multifamily_2_4") in types
