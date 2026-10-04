import re
from datetime import date

DECISIVE = ("min_units", "max_units", "construction_cutoff", "new_construction_exemption",
            "owner_occupied_exemption_max_units", "requires_unknown_facts")
OPS = {"on_or_before": "<=", "after": ">", "before": "<", "on_or_after": ">="}


def required_unknown_facts(rule):
    ruf = backed_coverage(rule).get("requires_unknown_facts")
    if isinstance(ruf, list):
        return [str(f).replace("_", " ").strip() for f in ruf if str(f).strip()]
    if ruf is not True:
        return []
    cc = rule.get("coverage_conditions") or {}
    text = (" ".join(str(cc.get(k) or "") for k in ("summary", "owner_conditions", "other_conditions"))
            if isinstance(cc, dict) else str(cc))
    labels = []
    if re.search(r"\b(convert(?:ed|ing|s|ion)?|condominium|cooperative)\b", text, re.I):
        labels.append("building conversion status")
    if re.search(r"\b(tenant|resident).{0,80}\b(age|aged|disab|income|lived|resid)", text, re.I):
        labels.append("tenant eligibility and occupancy history")
    if re.search(r"\b(DND|BPDA|program|funding|funded|affordable|income[- ]restricted|subsid)", text, re.I):
        labels.append("program or affordable-housing eligibility")
    if re.search(r"\b(owner|landlord).{0,60}\b(type|occup|portfolio|size)", text, re.I):
        labels.append("owner type or occupancy")
    return list(dict.fromkeys(labels)) or ["building eligibility facts specified by the rule"]


def _evidenced_fields(rule):
    out = set()
    for e in rule.get("coverage_evidence") or []:
        if isinstance(e, dict) and e.get("field") and str(e.get("quoted_span") or "").strip():
            f = str(e["field"])
            f = f[len("coverage."):] if f.startswith("coverage.") else f
            out.add(f.split(".")[0])
    return out


def backed_coverage(rule):
    cov = rule.get("coverage")
    if not isinstance(cov, dict):
        return {}
    ev = _evidenced_fields(rule)
    return {k: v for k, v in cov.items() if k in ev and v not in (None, [], {})}


def decisive_coverage(rule):
    return {
        k: v for k, v in backed_coverage(rule).items()
        if k in DECISIVE and not (k == "requires_unknown_facts" and v is False)
    }


def _coverage_review_failed(rule):
    return ((rule.get("verification") or {}).get("verdicts") or {}).get("coverage") == "not_supported"


def _evidence_supports_general_scope(rule):
    return backed_coverage(rule).get("requires_unknown_facts") is False


def coverage_review_blocks(rule):
    return (_coverage_review_failed(rule)
            and (bool(decisive_coverage(rule)) or not _evidence_supports_general_scope(rule)))


def has_v3_coverage(rule):
    return bool(decisive_coverage(rule)) or _coverage_review_failed(rule) or _evidence_supports_general_scope(rule)


def _cmp(a, op, b):
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def _cutoff(b, cc):
    from .verdict import _co_date, to_date
    op = OPS.get(cc.get("covered_if"))
    if op is None or not cc.get("date"):
        return None, "construction cutoff not machine readable"
    if cc.get("basis") == "certificate_of_occupancy":
        return _co_date(b, op, cc["date"])
    y = b.get("year_built")
    if y is None:
        return None, "year built is missing"
    c = to_date(cc["date"])
    a, z = _cmp(date(y, 1, 1), op, c), _cmp(date(y, 12, 31), op, c)
    if a == z:
        return a, None
    return None, f"built in {y}, the cutoff year of {c.isoformat()}; the exact construction date is not in the data"


def _new_construction(b, nc, as_of):
    n = nc.get("years")
    if n is None:
        return None, None
    y = b.get("year_built")
    if y is None:
        return None, f"year built is missing, so the {n}-year new construction exemption cannot be checked"
    if as_of.year - y - 1 >= n:
        return True, None
    if as_of.year - y < n:
        if nc.get("requires_owner_filing"):
            return None, f"built in {y}: exempt as new construction (under {n} years) only if the owner filed for it"
        return False, None
    return None, f"built in {y}: the building may or may not be under {n} years old (new construction exemption)"


def evaluate(b, rule, as_of):
    from .verdict import _units
    review_failed = _coverage_review_failed(rule)
    if coverage_review_blocks(rule):
        reason = "coverage requires review because its evidence was not supported"
        if str(rule.get("review_note") or "").strip():
            reason += f": {rule['review_note'].strip()}"
        return None, reason, ["Coverage review required."]
    cov = backed_coverage(rule)
    checks, notes = [], []
    if cov.get("min_units") is not None:
        checks.append(_units(b, ">=", cov["min_units"]))
    if cov.get("max_units") is not None:
        checks.append(_units(b, "<=", cov["max_units"]))
    if isinstance(cov.get("construction_cutoff"), dict):
        checks.append(_cutoff(b, cov["construction_cutoff"]))
    if isinstance(cov.get("new_construction_exemption"), dict):
        v = _new_construction(b, cov["new_construction_exemption"], as_of)
        if v != (None, None):
            checks.append(v)
    n = cov.get("owner_occupied_exemption_max_units")
    if n is not None:
        v, _ = _units(b, ">", n)
        if v is not True:
            checks.append((None, f"owner-occupied buildings of at most {n} units are exempt; owner occupancy is not "
                                 "in the data"))
    ruf = cov.get("requires_unknown_facts")
    if ruf is True or isinstance(ruf, list):
        facts = required_unknown_facts(rule)
        checks.append((None, "missing facts: " + "; ".join(facts)))
    for t in cov.get("unverifiable_exemptions") or []:
        notes.append(f"Not verifiable from the data: {t}")
    if cov.get("landlord_size_condition"):
        notes.append(f"Not verifiable from the data: {cov['landlord_size_condition']}")
    if review_failed:
        detail = str(rule.get("review_note") or "").strip()
        notes.append("Coverage review required." + (f" {detail}" if detail else ""))
    vals = [v for v, _ in checks]
    if False in vals:
        return False, None, notes
    if None in vals:
        return None, "; ".join(w for v, w in checks if v is None and w), notes
    return True, None, notes


def eval_time_v3(rule, as_of):
    from .verdict import to_date
    ifs, cve = to_date(rule.get("in_force_since")), to_date(rule.get("current_version_effective"))
    if ifs is None and cve is None or rule.get("status") in ("failed", "pending"):
        return None
    if cve is not None and as_of >= cve:
        return "in_force", None
    start = ifs if ifs is not None else to_date(rule.get("effective_date"))
    if start is None:
        if rule.get("requirement_is_new") is True:
            return "not_yet_effective", None
    elif as_of < start:
        has_proved_prior_version = (rule.get("requirement_is_new") is False
                                    and bool(str(rule.get("prior_version_note") or "").strip()))
        if ifs is not None or not has_proved_prior_version:
            return "not_yet_effective", None
    note = None
    if cve is not None:
        note = (f"An earlier version applied on {as_of.isoformat()}; the current version takes effect on "
                f"{cve.isoformat()}.")
        if rule.get("prior_version_note"):
            note += f" {rule['prior_version_note']}"
    return "in_force", note


def first_effective(rule):
    from .verdict import to_date
    ifs = to_date(rule.get("in_force_since"))
    if ifs is not None:
        return ifs
    if rule.get("requirement_is_new") is False and str(rule.get("prior_version_note") or "").strip():
        return None
    eff = to_date(rule.get("effective_date"))
    if eff is not None:
        return eff
    if rule.get("requirement_is_new") is True:
        return to_date(rule.get("current_version_effective"))
    return None
