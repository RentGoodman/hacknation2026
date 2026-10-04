import json
import re
from datetime import date
from functools import lru_cache

from .config import OUT_JSON

CONFIRMED = {"resolved", "resolved_by_source_dataset", "resolved_by_mod_iv_municipality"}
CANDIDATE = {"postal_only", "postal_fallback"}
UNKNOWN = {"no_place", "not_geocoded"}
KNOWN_STATUSES = CONFIRMED | CANDIDATE | UNKNOWN
NOT_IN_SOURCE = {"owner_type", "certificate_of_occupancy_date", "tenancy_start"}
OPS = {"<", "<=", ">", ">=", "==", "in"}


@lru_cache(maxsize=1)
def _data():
    data = json.loads(OUT_JSON.read_text())
    check_statuses(data)
    return data


def check_statuses(data):
    bad = {i: b["city_status"] for i, b in data.items() if b.get("city_status") not in KNOWN_STATUSES}
    if bad:
        raise ValueError(f"unmapped city_status: {bad}")


def get_building(address_id):
    return _data()[address_id]


def all_ids():
    return list(_data())


def _norm(j):
    j = " ".join((j or "").split())
    if "," in j:
        city, st = (p.strip() for p in j.rsplit(",", 1))
        return f"{city.title() if city.isupper() or city.islower() else city}, {st.upper()}"
    return j.upper()


def jurisdictions(address_id):
    return jurisdictions_record(get_building(address_id))


def jurisdictions_record(b):
    status = b["city_status"]
    if status in CONFIRMED:
        conf, city, cand = "confirmed", b["legal_city"], None
    elif status in CANDIDATE:
        conf, city, cand = "candidate", None, b.get("legal_city_candidate") or b.get("legal_city")
    elif status in UNKNOWN:
        conf, city, cand = "unknown", None, None
    else:
        raise ValueError(f"unmapped city_status {status!r}")
    return {"state": b["state"], "city": city, "city_status": status, "city_confidence": conf, "city_candidate": cand,
            "city_confidence_score": b.get("city_confidence")}


def matches_jurisdiction_record(b, rule_jurisdiction, rule_level):
    j = jurisdictions_record(b)
    target = _norm(rule_jurisdiction)
    if rule_level == "state":
        return "yes" if j["state"] == target else "no"
    if rule_level != "city":
        raise ValueError(f"rule_level must be 'state' or 'city', got {rule_level!r}")
    if not target.endswith(", " + j["state"]):
        return "no"
    if j["city_confidence"] == "confirmed":
        return "yes" if j["city"] == target else "no"
    if j["city_confidence"] == "candidate":
        return "unknown" if j["city_candidate"] == target else "no"
    return "unknown"


def matches_jurisdiction(address_id, rule_jurisdiction, rule_level):
    return matches_jurisdiction_record(get_building(address_id), rule_jurisdiction, rule_level)


TEXT_FACTS = {
    "subsidized": ("SUBSD", "SUBSIDIZED", "SECTION 8", "S- 8"),
    "elderly_housing": ("ELDERLY", "SENIOR"),
    "tenancy_in_common": ("TIC", "TENANCY IN COMMON", "TENANTS IN COMMON"),
}


def _text_fact(b, name):
    source = b.get(name + "_source")
    if b.get(name) is True:
        return True, source or "building record"
    for field in ("use_description", "use_code"):
        text = " ".join(str(b.get(field) or "").upper().replace("/", " ").split())
        for keyword in TEXT_FACTS[name]:
            found = f" {keyword} " in f" {text} " if keyword == "TIC" else keyword in text
            if found:
                return True, f"{field} {b.get(field)!r}"
    return None, None


def fact(address_id, name):
    return fact_record(get_building(address_id), name)


def fact_record(b, name):
    if name == "certificate_of_occupancy_date":
        lower, upper = b.get("co_date_min"), b.get("co_date_max")
        reason = "not_in_source" if lower is None and upper is None else "bounded_by_public_record"
        return {"value": None, "known": False, "lower_bound": None, "lower": lower, "upper": upper,
                "method": b.get("co_date_method"), "reason": reason}
    if name in TEXT_FACTS:
        value, method = _text_fact(b, name)
        return {"value": value, "known": value is True, "lower_bound": None, "method": method,
                "reason": "explicit_in_source" if value else "not_stated_in_source"}
    if name in NOT_IN_SOURCE:
        return {"value": None, "known": False, "lower_bound": None, "reason": "not_in_source"}
    if name not in b:
        raise KeyError(f"unknown fact {name!r}")
    value = b[name]
    interval = {}
    if name == "year_built":
        interval = {"lower": value, "upper": value if value is not None else b.get("year_built_max"),
                    "method": b.get("year_built_max_method")}
    elif name == "units":
        interval = {"lower": value if value is not None else b.get("units_min"),
                    "upper": value if value is not None else b.get("units_max"),
                    "method": b.get("units_method")}
    if value is not None:
        return {"value": value, "known": True, "lower_bound": None, "reason": "source_dataset", **interval}
    lower_bound = b.get("units_min") if name == "units" else None
    if name == "year_built" and b.get("year_built_max") is not None:
        reason = "upper_bound_from_public_record"
    else:
        reason = "lower_bound_from_use_description" if lower_bound is not None else "missing_in_source"
    return {"value": None, "known": False, "lower_bound": lower_bound, "reason": reason, **interval}


def _tv(x):
    return "true" if x else "false"


def _to_date(v):
    if isinstance(v, date):
        return v
    if isinstance(v, int):
        return date(v, 1, 1)
    parts = str(v).split("-") + ["01", "01"]
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def _minus_years(value, years):
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _relative_years(value):
    if isinstance(value, dict) and "as_of_minus_years" in value:
        return int(value["as_of_minus_years"])
    if isinstance(value, str):
        match = re.fullmatch(r"\s*as_of\s*-\s*(\d+)\s*y\s*", value)
        if match:
            return int(match.group(1))
    return None


def _interval(lower, upper, op, value):
    if op == "in":
        values = list(value)
        if lower is not None and lower == upper:
            return _tv(lower in values)
        if not any((lower is None or item >= lower) and (upper is None or item <= upper) for item in values):
            return "false"
        return "unknown"
    if op == "==":
        if lower is not None and lower == upper:
            return _tv(lower == value)
        if (lower is not None and value < lower) or (upper is not None and value > upper):
            return "false"
        return "unknown"
    if op in ("<", "<="):
        compare = (lambda item: item < value) if op == "<" else (lambda item: item <= value)
        if upper is not None and compare(upper):
            return "true"
        if lower is not None and not compare(lower):
            return "false"
        return "unknown"
    compare = (lambda item: item > value) if op == ">" else (lambda item: item >= value)
    if lower is not None and compare(lower):
        return "true"
    if upper is not None and not compare(upper):
        return "false"
    return "unknown"


def check(address_id, fact_name, op, value, as_of="2026-10-01"):
    return check_record(get_building(address_id), fact_name, op, value, as_of=as_of)


def check_record(b, fact_name, op, value, as_of="2026-10-01"):
    if op not in OPS:
        raise ValueError(f"unsupported op {op!r}")
    as_of_date = _to_date(as_of)
    if fact_name == "certificate_of_occupancy_date":
        lower, upper = b.get("co_date_min"), b.get("co_date_max")
        if lower is None and upper is None:
            return "unknown"
        lower = _to_date(lower) if lower is not None else None
        upper = _to_date(upper) if upper is not None else None

        def date_value(item):
            relative = _relative_years(item)
            return _minus_years(as_of_date, relative) if relative is not None else _to_date(item)

        target = [date_value(item) for item in value] if op == "in" else date_value(value)
        return _interval(lower, upper, op, target)
    if fact_name == "year_built":
        year = b.get("year_built")
        lower, upper = (year, year) if year is not None else (None, b.get("year_built_max"))
        if lower is None and upper is None:
            return "unknown"

        def year_value(item):
            relative = _relative_years(item)
            if relative is not None:
                return as_of_date.year - relative
            return int(item) if isinstance(item, str) and item.isdigit() else item

        target = [year_value(item) for item in value] if op == "in" else year_value(value)
        return _interval(lower, upper, op, target)
    if fact_name == "units":
        units = b.get("units")
        lower, upper = (units, units) if units is not None else (b.get("units_min"), b.get("units_max"))
        if lower is None and upper is None:
            return "unknown"
        if op == "in" and lower is not None and upper is not None and upper - lower <= 10_000:
            outcomes = {item in value for item in range(lower, upper + 1)}
            if outcomes == {True}:
                return "true"
            if outcomes == {False}:
                return "false"
            return "unknown"
        return _interval(lower, upper, op, value)
    item = fact_record(b, fact_name)
    if not item["known"]:
        return "unknown"
    return _interval(item["value"], item["value"], op, value)
