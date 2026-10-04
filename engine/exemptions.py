import re

from .classify_conditions import NATURES, heuristic_v6
from .conditions import _shown

OWNER_FACT = "owner type / owner occupancy"
UNITS_FACT = "unit count"
TYPE_FACT = "property type"
AFFORDABLE_FACT = "subsidized or affordable status"
UNIT_COUNT_BY_PROPERTY_TYPE = {"single_family": 1, "duplex": 2, "triplex": 3}
NON_APARTMENT_PROPERTY_TYPES = {"condo", "townhome", "mobile_home", "room_in_owner_home"}
UNUSUAL_PROPERTY_TYPES = {"hotel", "care_facility", "dormitory", "other"}
AFFORDABLE = re.compile(r"\b(affordable|deed[- ]restricted|subsidi[sz]ed|subsidy|income[- ]restricted|low[- ]income|"
                        r"IDP|DND|inclusionary|public housing)\b", re.I)


def _apartment(b):
    return str(b.get("property_type") or "").startswith(("multifamily", "mixed_use"))


def _unit_count_status(building, required_units):
    recorded_units = building.get("units")
    if recorded_units is not None:
        return recorded_units == required_units, None

    minimum_units = building.get("units_min")
    maximum_units = building.get("units_max")
    if minimum_units is not None and minimum_units > required_units:
        return False, None
    if maximum_units is not None and maximum_units < required_units:
        return False, None
    if minimum_units == maximum_units == required_units:
        return True, None
    return None, UNITS_FACT


def _recorded_property_type_status(building, target_type):
    recorded_type = building.get("property_type")
    if recorded_type == target_type:
        return True, None
    if _apartment(building) or recorded_type is not None:
        return False, None
    return None, TYPE_FACT


def _property_type_status(building, target_type):
    if target_type == "single_family" and _apartment(building):
        return False, None
    if target_type in UNIT_COUNT_BY_PROPERTY_TYPE:
        return _unit_count_status(building, UNIT_COUNT_BY_PROPERTY_TYPE[target_type])
    if target_type in NON_APARTMENT_PROPERTY_TYPES | UNUSUAL_PROPERTY_TYPES:
        return _recorded_property_type_status(building, target_type)
    return False, None


def _owner_status(b, c):
    units, lo, hi = b.get("units"), b.get("units_min"), b.get("units_max")
    bound = c.get("owner_exemption_max_units")
    if bound is None and c.get("nature_source") == "v5":
        bound = c.get("units_max")
    if bound is not None:
        n = units if units is not None else lo
        if n is not None and n > bound:
            return "impossible", f"it cannot apply at {_shown(units, lo, hi)}, it requires at most {bound} units"
        m = units if units is not None else hi
        if m is not None and m <= bound:
            return "unknown", [OWNER_FACT]
        return "unknown", [OWNER_FACT, UNITS_FACT]
    types = [t for t in c.get("property_types_targeted") or [] if t not in UNUSUAL_PROPERTY_TYPES]
    if types:
        st = [_property_type_status(b, t) for t in types]
        if all(v is False for v, _ in st):
            return "impossible", (f"it targets {', '.join(t.replace('_', ' ') for t in types)}, not this building "
                                  f"(property type {b.get('property_type')}, {_shown(units, lo, hi)})")
        if any(v is True for v, _ in st):
            return "unknown", [OWNER_FACT]
        return "unknown", list(dict.fromkeys([OWNER_FACT] + [f for v, f in st if v is None]))
    return "unknown", [OWNER_FACT]


def _exemption(b, c, label, text):
    if c.get("can_exclude_apartment_building") is False and _apartment(b):
        return "applies", (f"The {label} cannot apply to this building "
                           f"(property type {b.get('property_type')}); it is also an unusual situation, not assumed: "
                           f"{text}"), []
    if c.get("situation") == "unusual" and not c.get("property_types_targeted"):
        return "applies", f"Applies unless {label} (an unusual situation, not assumed): {text}", []
    facts, detail = [], None
    if c.get("owner_linked"):
        state, info = _owner_status(b, c)
        if state == "unknown":
            facts += info
        if state == "impossible":
            return "applies", f"The {label} cannot apply at {_shown(b.get('units'), b.get('units_min'), b.get('units_max'))}: {text} ({info})", []
    else:
        units, lo, hi, um = b.get("units"), b.get("units_min"), b.get("units_max"), c.get("units_max")
        if um is not None:
            n, m = (units, units) if units is not None else (lo, hi)
            if m is not None and m <= um:
                return "excluded", f"Excluded by {label} (at most {um} units, {_shown(units, lo, hi)}): {text}", []
            if n is None or n <= um:
                facts.append(UNITS_FACT)
            else:
                detail = f"it cannot apply at {_shown(units, lo, hi)}, it covers at most {um} units"
        types = c.get("property_types_targeted") or []
        st = [(t,) + _property_type_status(b, t) for t in types]
        hit = next((t for t, v, _ in st if v is True), None)
        if hit:
            return "excluded", f"Excluded by {label} (the building is a {hit.replace('_', ' ')}): {text}", []
        facts += [f for _, v, f in st if v is None]
        if types and not facts and detail is None:
            detail = f"it cannot apply to this building (property type {b.get('property_type')})"
    if c.get("affordable_targeted") and b.get("subsidized") is True:
        facts.append(AFFORDABLE_FACT)
    if facts:
        return "unknown", (f"{label} may apply and is not verifiable "
                           f"({', '.join(dict.fromkeys(facts))} not in the data): {text}"), facts
    if c.get("situation") == "unusual":
        return "applies", f"Applies unless {label} (an unusual situation, not assumed): {text}", []
    if detail:
        return "applies", (f"The {label} cannot apply at "
                           f"{_shown(b.get('units'), b.get('units_min'), b.get('units_max'))}: {text} ({detail})"), []
    return "applies", f"Applies unless {label}: {text}", []


def _reference(c, label, text, positive):
    name = c.get("references") or label
    fact = f"referenced ordinance coverage: {name}"
    rv, rwhy, rid = c.get("_ref_result") or (None, "referenced rule not resolved", None)
    if rid is None:
        if not positive:
            return "applies", f"Applies unless {label} (referenced {name}: {rwhy}): {text}", []
        if "_self_regime" not in c:
            return "unknown", f"{label}: coverage of the referenced {name} is unknown ({rwhy}): {text}", [fact]
        rv, rwhy = c["_self_regime"]
        rid = "this rule's own regime coverage"
    if rv is None:
        return "unknown", (f"{label}: coverage of the referenced {name} ({rid}) is unknown "
                           f"({rwhy or 'no machine-readable coverage'})"), [fact]
    if positive:
        return ("applies", f"Covered by the referenced {name} ({rid}): {text}", []) if rv else \
            ("excluded", f"Not covered by the referenced {name} ({rid}): {text}", [])
    return ("excluded", f"Excluded: covered by the referenced {name} ({rid}) instead: {text}", []) if rv else \
        ("applies", f"Not covered by the referenced {name} ({rid}), so this rule applies: {text}", [])


def _positive(b, c, label, text):
    types = c.get("property_types_targeted") or []
    st = [_property_type_status(b, t) for t in types]
    if types and all(v is False for v, _ in st):
        return "excluded", (f"Not covered: {label} (property type {b.get('property_type')}, "
                            f"{_shown(b.get('units'), b.get('units_min'), b.get('units_max'))}): {text}"), []
    if c.get("situation") == "references_coverage":
        return _reference(c, label, text, True)
    facts = [f for v, f in st if v is None]
    facts.append(OWNER_FACT if c.get("owner_linked") else AFFORDABLE_FACT if AFFORDABLE.search(text) else label)
    return "unknown", f"{label} not verifiable from the data: {text}", facts


def evaluate_conditions(b, conds, cov, cov_why):
    notes, reasons, facts, excluded = [], [], [], False
    for raw in conds or []:
        c = raw if raw.get("nature") in NATURES else {**raw, **heuristic_v6(raw), "nature_source": "v5"}
        text, label = c["text"].strip(), c.get("label") or "condition"
        nature = c["nature"]
        if nature in ("modifies_terms", "informational"):
            units, lo, hi = b.get("units"), b.get("units_min"), b.get("units_max")
            n = units if units is not None else lo
            if c.get("units_max") is not None and n is not None and n > c["units_max"]:
                notes.append(f"The {label} cannot apply at {_shown(units, lo, hi)} "
                             f"(it requires at most {c['units_max']} units): {text}")
            else:
                notes.append(f"{'Terms may differ' if nature == 'modifies_terms' else 'Note'}: {text}")
            continue
        positive = nature == "positive_limit"
        if positive:
            state, msg, f = _positive(b, c, label, text)
        elif c.get("situation") == "references_coverage":
            state, msg, f = _reference(c, label, text, False)
        else:
            state, msg, f = _exemption(b, c, label, text)
        if state == "unknown":
            reasons.append(msg)
            facts += f
        else:
            notes.append(msg)
            excluded = excluded or state == "excluded"
    if cov is False or excluded:
        return False, (None if excluded else cov_why), notes, []
    if reasons:
        return None, "; ".join(([cov_why] if cov is None and cov_why else []) + reasons), notes, \
            list(dict.fromkeys(facts))
    return cov, cov_why, notes, []
