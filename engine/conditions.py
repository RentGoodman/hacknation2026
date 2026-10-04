def _shown(units, lo, hi):
    if units is not None:
        return f"{units} units"
    return f"{lo} to {hi} units" if hi is not None else f"at least {lo} units"


def apply_conditions(b, conds, cov, cov_why):
    from .exemptions import evaluate_conditions
    cov, why, notes, _ = evaluate_conditions(b, conds, cov, cov_why)
    return cov, why, notes


def apply_conditions_v5(b, conds, cov, cov_why):
    notes, reasons = [], []
    for c in conds:
        text = c["text"].strip()
        units, lo, hi = b.get("units"), b.get("units_min"), b.get("units_max")
        n = units if units is not None else lo
        ruled_out = c.get("units_max") is not None and n is not None and n > c["units_max"]
        if c["effect"] != "excludes_coverage":
            if ruled_out:
                shown = _shown(units, lo, hi)
                notes.append(f"The {c.get('label') or 'condition'} cannot apply at {shown} "
                             f"(it requires at most {c['units_max']} units): {text}")
            else:
                notes.append(f"{'Terms may differ' if c['effect'] == 'modifies_terms' else 'Note'}: {text}")
            continue
        situation = c.get("situation")
        if situation == "unusual":
            notes.append(f"Applies unless the {c.get('label') or 'exemption'} holds (an unusual situation, not "
                         f"assumed): {text}")
            continue
        if situation == "references_coverage" and "_ref_result" in c:
            rv, rwhy, rid = c["_ref_result"]
            if rv is True:
                notes.append(f"Covered by the referenced rule {rid} ({c.get('references')}): {text}")
                continue
            if rv is False:
                return False, None, notes
            reasons.append(f"{c.get('label') or 'condition'}: coverage of the referenced {c.get('references')} "
                           f"({rid or 'rule not found'}) is unknown ({rwhy or 'no machine-readable coverage'})")
            continue
        apartment = str(b.get("property_type") or "").startswith(("multifamily", "mixed_use"))
        if c.get("can_exclude_apartment_building") is False and apartment:
            notes.append(f"The {c.get('label') or 'exclusion'} cannot apply to this building "
                         f"(property type {b.get('property_type')}): {text}")
            continue
        if ruled_out:
            shown = _shown(units, lo, hi)
            notes.append(f"The {c.get('label') or 'condition'} cannot apply at {shown} "
                         f"(it requires at most {c['units_max']} units): {text}")
            continue
        reasons.append(f"{c.get('label') or 'condition'} not verifiable from the data: {text}")
    if reasons and cov is True:
        return None, "; ".join(reasons), notes
    if reasons and cov is None:
        return None, "; ".join([cov_why] + reasons), notes
    return cov, cov_why, notes
