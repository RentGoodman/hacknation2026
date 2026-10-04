import json
import re
from pathlib import Path

USE_CODE_MAP = json.loads((Path(__file__).resolve().parent / "use_code_map.json").read_text())
ALWAYS_MISSING = ["owner_type"]
CO_DATE_METHOD = "year_built proxy (year built is not the certificate date; cutoff-year buildings stay unknown)"


def to_int(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return int(f) if f == int(f) else None


ZIP_FIRST_DIGIT = {"CA": "9", "NJ": "0", "MA": "0"}


NJ_DS = "NJOGIS"


UNIT_TOKEN = re.compile(r"(\d[\dO]*)\s*U(?![A-Z])")


def explicit_units(desc, source_dataset):
    if not (source_dataset or "").startswith(NJ_DS):
        return None, None
    per_building = {}
    for segment in (desc or "").upper().split("/"):
        counts = [int(tok.replace("O", "0")) for tok in UNIT_TOKEN.findall(segment)]
        if counts:
            key = segment.strip().removesuffix("-G")
            per_building[key] = max(counts + [per_building.get(key, 0)])
    if not per_building:
        return None, None
    return sum(per_building.values()), desc


NUMBER_WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10}
_N = r"(\d+|" + "|".join(NUMBER_WORDS) + r")"
_UNITS = r"[\s-]*UNITS?"
UNIT_BOUND = re.compile("|".join((
    rf"(?P<lo>{_N})\s*(?:-|TO)\s*(?P<hi>{_N}){_UNITS}",
    rf">\s*(?P<over>{_N}){_UNITS}",
    rf"\(?(?P<least>{_N})\s*(?:\+{_UNITS}\)?|(?:{_UNITS})?\s+OR\s+MORE)",
    rf"(?P<most>{_N}){_UNITS}\s+OR\s+(?:LESS|FEWER)",
)), re.I)


def _num(s):
    return NUMBER_WORDS.get(s.upper()) or int(s)


def range_units(desc):
    m = UNIT_BOUND.search(desc or "")
    if not m:
        return None
    g = {k: _num(v) for k, v in m.groupdict().items() if v}
    if "lo" in g:
        return g["lo"], g["hi"], m.group(0)
    if "over" in g:
        return g["over"] + 1, None, m.group(0)
    if "least" in g:
        return g["least"], None, m.group(0)
    return None, g["most"], m.group(0)


CLASS_UNITS = (
    (NJ_DS, "4C", 5, None, "NJ MOD-IV"),
    ("Boston", "A/", 7, None, "Boston"),
    ("Cambridge", "111", 4, 8, "Cambridge"),
)


def class_units(source_dataset, use_code):
    ds, code = source_dataset or "", (use_code or "").strip().upper()
    for prefix, c, lo, hi, label in CLASS_UNITS:
        if ds.startswith(prefix) and (code.startswith(c) if c.endswith("/") else code == c):
            return lo, hi, label
    return None


def units_interval(row):
    raw = to_int(row["units"])
    desc, ds, code = row["use_description"], row["source_dataset"], row["use_code"]
    rng, cls = range_units(desc), class_units(ds, code)
    n, txt = explicit_units(desc, ds)
    bound = None
    if rng:
        bound = (rng[0], rng[1], f"range in use_description ({rng[2]})")
    elif cls:
        bound = (cls[0], cls[1], f"class: {cls[2]} use_code {code}")

    def outside(v, b):
        return b is not None and ((b[0] is not None and v < b[0]) or (b[1] is not None and v > b[1]))

    def include_value(interval, value):
        lo, hi = interval
        return (None if lo is None else min(lo, value),
                None if hi is None else max(hi, value))

    def set_interval(interval, method, conflicting=()):
        lo, hi = interval
        notes = []
        for label, value in conflicting:
            lo, hi = include_value((lo, hi), value)
            notes.append(f"{label} {value}")
        suffix = "; interval widened to include conflicting " + " and ".join(notes) if notes else ""
        out.update(units_min=lo, units_max=hi, units_method=method + suffix)

    out = {"units": raw, "units_raw": raw, "units_conflict": False}
    raw_conflict = raw is not None and (outside(raw, bound) or (n is not None and raw != n))
    if raw is not None:
        if raw_conflict:
            out.update(units=None, units_conflict=True)
        else:
            out.update(units_min=raw, units_max=raw, units_method="csv units field")
            return out
    if n is not None:
        cb = (cls[0], cls[1], f"class: {cls[2]} use_code {code}") if cls else None
        if outside(n, cb) or outside(n, rng and (rng[0], rng[1])):
            out.update(units_conflict=True)
            conflicts = [("explicit description count", n)]
            if raw_conflict:
                conflicts.append(("CSV units", raw))
            set_interval((bound[0], bound[1]), bound[2], conflicts)
        else:
            conflicts = [("CSV units", raw)] if raw_conflict else []
            set_interval((n, n), f"explicit count in use_description ({txt})", conflicts)
        return out
    if bound:
        conflicts = [("CSV units", raw)] if raw_conflict else []
        set_interval((bound[0], bound[1]), bound[2], conflicts)
    else:
        out.update(units_min=None, units_max=None, units_method="not in public record")
    return out


def zip_suspect(state, zip_code, source_dataset=""):
    z = (zip_code or "").strip()
    if z and (source_dataset or "").startswith(NJ_DS):
        return True
    return bool(z) and not z.startswith(ZIP_FIRST_DIGIT[state])


def property_type(source_dataset, use_code):
    return (USE_CODE_MAP.get(source_dataset) or {}).get(use_code)


def threshold_year_case(year, legal_city):
    return (legal_city == "Los Angeles, CA" and year == 1978) or (legal_city == "San Francisco, CA" and year == 1979)


def co_dates(year):
    if year is None:
        return {"co_date_min": None, "co_date_max": None, "co_date_method": None}
    return {"co_date_min": f"{year}-01-01", "co_date_max": f"{year}-12-31", "co_date_method": CO_DATE_METHOD}


def text_flags(source_dataset, use_description):
    d = (use_description or "").upper()
    hits = {
        "subsidized": re.search(r"SUBSD|S-\s?8\b", d),
        "elderly_housing": re.search(r"ELDERLY HOME", d),
        "tenancy_in_common": re.search(r"\bTIC\b", d),
    }
    out = {}
    for k, m in hits.items():
        out[k] = True if m else None
        out[k + "_source"] = f"use_description '{use_description}' ({source_dataset})" if m else None
    return out


def facts(row, extra=None):
    year = to_int(row["year_built"])
    year_method = "csv year_built" if year is not None else None
    if year is None and extra and extra.get("year_built") is not None:
        year = extra["year_built"]
        year_method = f"{extra['enrichment_method']} [{extra['enrichment_source']}]"
    u = units_interval(row)
    units = u["units"]
    ptype = property_type(row["source_dataset"], row["use_code"])
    missing = [k for k, v in (("year_built", year), ("units", units), ("property_type", ptype)) if v is None]
    co = co_dates(year)
    if co["co_date_min"] is None:
        missing.append("certificate_of_occupancy_date")
    return {
        "year_built": year,
        "year_built_method": year_method,
        "ambiguous_year": bool(extra and extra.get("ambiguous_year")),
        "units": units,
        "use_code": row["use_code"],
        "use_description": row["use_description"],
        "units_raw": u["units_raw"],
        "units_min": u["units_min"],
        "units_max": u["units_max"],
        "units_method": u["units_method"],
        "units_conflict": u["units_conflict"],
        "source_dataset": row["source_dataset"],
        "zip_suspect": zip_suspect(row["state"], row["zip"], row["source_dataset"]),
        "property_type": ptype,
        "missing_facts": missing + ALWAYS_MISSING,
        **co,
        **text_flags(row["source_dataset"], row["use_description"]),
    }
