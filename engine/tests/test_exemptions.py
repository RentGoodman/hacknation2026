from engine.classify_conditions import heuristic_v6, validate_v6
from engine.exemptions import AFFORDABLE_FACT, OWNER_FACT, evaluate_conditions


def bldg(**kw):
    b = {"state": "CA", "legal_city": "Los Angeles, CA", "year_built": 1950, "units": 20, "units_min": 20,
         "units_max": 20, "property_type": "multifamily_5plus", "subsidized": None, "threshold_year_case": False}
    return {**b, **kw}


def cond(**kw):
    c = {"field": "exemptions", "text": "t", "nature": "exemption", "owner_linked": False,
         "owner_exemption_max_units": None, "owner_units_clause": None, "property_types_targeted": [],
         "affordable_targeted": False, "situation": "ordinary", "references": None, "label": "x"}
    return {**c, **kw}


OWNER = dict(owner_linked=True, owner_exemption_max_units=3, owner_units_clause="1-3 unit property",
             label="owner-occupied exemption", text="Exempt if an owner of record resides in a 1-3 unit property.")


def test_owner_exemption_on_20_units_applies_with_note():
    cov, why, notes, missing = evaluate_conditions(bldg(), [cond(**OWNER)], True, None)
    assert cov is True and missing == [] and "cannot apply at 20 units" in notes[0]


def test_owner_exemption_within_bound_is_unknown_with_owner_fact():
    b = bldg(units=2, units_min=2, units_max=2, property_type="multifamily")
    cov, why, notes, missing = evaluate_conditions(b, [cond(**OWNER)], True, None)
    assert cov is None and missing == [OWNER_FACT] and "owner-occupied exemption" in why


def test_owner_exemption_units_unknown_on_multifamily_is_unknown():
    b = bldg(units=None, units_min=None, units_max=None, property_type="multifamily")
    cov, why, notes, missing = evaluate_conditions(b, [cond(**OWNER)], True, None)
    assert cov is None and notes == [] and missing == [OWNER_FACT, "unit count"]
    assert "owner-occupied exemption may apply" in why


def test_owner_exemption_without_bound_on_multifamily_is_unknown():
    c = cond(owner_linked=True, label="owner-based exemptions", text="Same owner-based exemptions.")
    cov, why, notes, missing = evaluate_conditions(bldg(), [c], True, None)
    assert cov is None and notes == [] and missing == [OWNER_FACT]
    assert "owner-based exemptions may apply" in why


def test_owner_duplex_type_on_two_units_is_unknown():
    c = cond(owner_linked=True, property_types_targeted=["duplex"], label="owner-occupied duplex")
    b = bldg(units=2, units_min=2, units_max=2, property_type="multifamily")
    assert evaluate_conditions(b, [c], True, None)[3] == [OWNER_FACT]
    assert evaluate_conditions(bldg(), [c], True, None)[0] is True


def test_townhome_exemption_on_multifamily_applies():
    c = cond(property_types_targeted=["condo", "townhome"], label="condo/townhome exemption")
    cov, _, notes, missing = evaluate_conditions(bldg(), [c], True, None)
    assert cov is True and missing == [] and "cannot apply to this building" in notes[0]


def test_two_family_type_exemption_excludes_a_two_unit_building():
    c = cond(property_types_targeted=["single_family", "duplex"], label="one- or two-family exemption")
    b = bldg(units=2, units_min=2, units_max=2, property_type="multifamily")
    assert evaluate_conditions(b, [c], True, None)[0] is False
    b = bldg(units=None, units_min=2, units_max=6, property_type="multifamily")
    assert evaluate_conditions(b, [c], True, None)[3] == ["unit count"]


def test_subsidized_positive_limit_is_unknown():
    c = cond(nature="positive_limit", situation="restricted_coverage", label="subsidized units only",
             text="Only where there is a government rent subsidy.")
    cov, why, _, missing = evaluate_conditions(bldg(), [c], True, None)
    assert cov is None and "subsidized units only" in why and missing == [AFFORDABLE_FACT]


def test_affordable_exemption_unknown_only_when_record_flags_subsidy():
    c = cond(affordable_targeted=True, label="affordable housing exemption", text="Deed-restricted housing.")
    assert evaluate_conditions(bldg(), [c], True, None)[0] is True
    assert evaluate_conditions(bldg(subsidized=True), [c], True, None)[3] == [AFFORDABLE_FACT]


def test_shared_kitchen_applies_with_note():
    c = cond(situation="unusual", owner_linked=True, label="shared kitchen exemption",
             text="Units where the owner shares a kitchen or bath with the tenant.")
    cov, _, notes, missing = evaluate_conditions(bldg(), [c], True, None)
    assert cov is True and missing == [] and "shared kitchen exemption" in notes[0]


def test_exemption_reference_polarity():
    c = cond(situation="references_coverage", references="RSO", label="RSO units covered elsewhere")
    assert evaluate_conditions(bldg(), [dict(c, _ref_result=(True, None, "rso"))], True, None)[0] is False
    cov, _, notes, _ = evaluate_conditions(bldg(), [dict(c, _ref_result=(False, None, "rso"))], True, None)
    assert cov is True and "Not covered by the referenced RSO" in notes[0]
    cov, why, _, missing = evaluate_conditions(bldg(), [dict(c, _ref_result=(None, "unit count", "rso"))], True, None)
    assert cov is None and "unit count" in why and missing == ["referenced ordinance coverage: RSO"]


def test_positive_reference_polarity_and_self_regime():
    c = cond(nature="positive_limit", situation="references_coverage", references="RSO", label="RSO units only")
    assert evaluate_conditions(bldg(), [dict(c, _ref_result=(True, None, "rso"))], True, None)[0] is True
    assert evaluate_conditions(bldg(), [dict(c, _ref_result=(False, None, "rso"))], True, None)[0] is False
    nf = dict(c, _ref_result=(None, "referenced rule not found", None))
    assert evaluate_conditions(bldg(), [nf], True, None)[0] is None
    assert evaluate_conditions(bldg(), [dict(nf, _self_regime=(True, None))], True, None)[0] is True
    assert evaluate_conditions(bldg(), [dict(nf, _self_regime=(False, None))], True, None)[0] is False


def test_positive_limit_on_impossible_property_type_is_excluded():
    c = cond(nature="positive_limit", situation="references_coverage", references="JCO",
             property_types_targeted=["single_family"], label="single-family JCO dwellings only")
    assert evaluate_conditions(bldg(), [c], True, None)[0] is False


def test_combination_and_incoming_coverage():
    pos = cond(nature="positive_limit", situation="restricted_coverage", label="program units only")
    cov, why, _, missing = evaluate_conditions(bldg(), [pos, pos], None, "year built is missing")
    assert cov is None and why.startswith("year built is missing; ") and missing == ["program units only"]
    assert evaluate_conditions(bldg(), [pos], False, None) == (False, None, [], [])
    excl = dict(cond(), _ref_result=(True, None, "rso"), situation="references_coverage")
    cov, why, notes, missing = evaluate_conditions(bldg(), [pos, excl], True, None)
    assert (cov, why, missing) == (False, None, []) and notes[0].startswith("Excluded: covered by")
    assert evaluate_conditions(bldg(), [cond(nature="modifies_terms", text="Deadline differs.")], True, None)[:3] == \
        (True, None, ["Terms may differ: Deadline differs."])


def test_v5_only_condition_dicts_still_work():
    v5 = {"field": "owner_conditions", "effect": "excludes_coverage", "units_max": 3,
          "units_clause": "1-3 unit property", "can_exclude_apartment_building": True, "situation": "ordinary",
          "references": None, "label": "owner-occupied 1-3 units",
          "text": "Exempt if an owner of record resides in one of the units (1-3 unit property)."}
    assert evaluate_conditions(bldg(), [v5], True, None)[0] is True
    b = bldg(units=3, units_min=3, units_max=3, property_type="multifamily")
    assert evaluate_conditions(b, [v5], True, None)[3] == [OWNER_FACT]
    restricted = dict(v5, situation="restricted_coverage", units_max=None, label="IDP units only",
                      text="Applies to income-restricted units under the IDP.")
    assert evaluate_conditions(bldg(), [restricted], True, None)[0] is None
    jco = dict(v5, situation="references_coverage", references="RSO", units_max=None, label="RSO elsewhere",
               text="Units subject to the RSO are covered by that ordinance instead.", _ref_result=(True, None, "r"))
    assert evaluate_conditions(bldg(), [jco], True, None)[0] is False
    terms = dict(v5, effect="modifies_terms", situation=None, units_max=None, text="Small landlords may charge more.")
    assert evaluate_conditions(bldg(), [terms], True, None)[:2] == (True, None)


def test_heuristic_v6_is_deterministic_and_maps_keywords():
    c = {"field": "exemptions", "effect": "excludes_coverage", "situation": "ordinary", "units_max": None,
         "label": "x", "text": "Owner-occupied duplexes and condominiums are exempt."}
    a, b = heuristic_v6(c), heuristic_v6(dict(c))
    assert a == b and a["nature"] == "exemption" and a["owner_linked"] is True
    assert a["property_types_targeted"] == ["condo", "duplex"]
    p = heuristic_v6({"field": "other_conditions", "text": "Applies only to subsidized units in the program."})
    assert p["nature"] == "positive_limit" and p["situation"] == "restricted_coverage"
    r = heuristic_v6(dict(c, situation="references_coverage", references="RSO",
                          text="Units subject to the RSO are covered by that ordinance instead."))
    assert r["nature"] == "exemption" and r["references"] == "RSO"
    assert heuristic_v6(dict(c, effect="modifies_terms", text="May charge two months."))["nature"] == "modifies_terms"
    subpart = heuristic_v6({"field": "other_conditions",
                            "text": "Subd. (o) applies only where there is a government rent subsidy."})
    assert subpart["nature"] == "modifies_terms"


def test_validate_v6_rejects_non_verbatim_owner_clause():
    c = {"nature": "exemption", "owner_linked": True, "owner_exemption_max_units": 4,
         "owner_units_clause": "four units or fewer", "property_types_targeted": ["duplex", "castle"]}
    v, rejected = validate_v6(c, "Owner-occupied premises of not more than four dwelling units.")
    assert v["owner_exemption_max_units"] is None and v["property_types_targeted"] == ["duplex"]
    assert len(rejected) == 2
    v, rejected = validate_v6(dict(c, owner_units_clause="not more than four dwelling units"),
                              "Owner-occupied premises of not more than  four dwelling units.")
    assert v["owner_exemption_max_units"] == 4
