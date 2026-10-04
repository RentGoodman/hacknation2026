import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"

FACT_PATTERNS = [
    (re.compile(r"legal city|city_status", re.I), "legal_city"),
    (re.compile(r"coverage not machine readable", re.I), "coverage_not_machine_readable"),
    (re.compile(r"unit count", re.I), "units"),
    (re.compile(r"certificate of occupancy|year built|building age", re.I),
     "year_built / certificate_of_occupancy_date"),
    (re.compile(r"owner type", re.I), "owner_type"),
    (re.compile(r"tenancy start", re.I), "tenancy_start"),
]
CONDITION = re.compile(r"([A-Za-z][\w -]*?) not verifiable from the data", re.I)


def missing_fact(explanation):
    text = explanation or ""
    for pat, fact in FACT_PATTERNS:
        if pat.search(text):
            return fact
    m = CONDITION.search(text)
    if m:
        return "condition: " + m.group(1).strip().lower()
    return "other"


def _city(b):
    return (b or {}).get("legal_city") or (b or {}).get("legal_city_candidate") or (b or {}).get("state") or "unknown"


def _address(b, aid):
    b = b or {}
    return b.get("normalized_address") or b.get("input_address") or aid


def _facts(entry, aid, detail):
    d = (((detail or {}).get("addresses") or {}).get(aid) or {}).get("rules", {}).get(entry["team_rule_id"]) or {}
    facts = [f for f in (d.get("missing_facts") or []) if f]
    return list(dict.fromkeys(facts)) or [missing_fact(entry.get("explanation"))]


def compute(lookups, buildings, detail=None):
    groups = defaultdict(lambda: {"answers": 0, "buildings": set(), "rules": set(), "example": None})
    for aid in sorted(lookups):
        b = buildings.get(aid)
        for e in lookups[aid]:
            if e.get("result") != "unknown":
                continue
            for fact in _facts(e, aid, detail):
                g = groups[(fact, _city(b))]
                g["answers"] += 1
                g["buildings"].add(aid)
                g["rules"].add(e["team_rule_id"])
                if g["example"] is None:
                    g["example"] = _address(b, aid)
    out = [{"missing_fact": f, "city": c, "unknown_answers": g["answers"], "buildings": len(g["buildings"]),
            "rules": sorted(g["rules"]), "example_address": g["example"]} for (f, c), g in groups.items()]
    out.sort(key=lambda r: (-r["unknown_answers"], -r["buildings"], r["missing_fact"], r["city"]))
    return out


def load(out_dir=OUT):
    lk = json.loads((out_dir / "lookups.json").read_text())
    lk = lk.get("lookups", lk)
    bl = json.loads((out_dir / "buildings.json").read_text())
    if isinstance(bl, list):
        bl = {b["address_id"]: b for b in bl}
    return lk, bl


def load_detail(out_dir=OUT):
    try:
        return json.loads((out_dir / "lookups_detail.json").read_text())
    except (OSError, ValueError):
        return None


def compute_from_out(out_dir=OUT):
    return compute(*load(out_dir), detail=load_detail(out_dir))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    detail = load_detail()
    rows = compute(*load(), detail=detail)
    print("missing facts from " + ("out/lookups_detail.json" if detail else "explanation text (no detail file)"))
    if "--dry-run" in argv:
        for r in rows[:10]:
            print(f"{r['unknown_answers']:5d} answers {r['buildings']:4d} bldgs  {r['missing_fact']} | {r['city']}"
                  f" | {len(r['rules'])} rules | e.g. {r['example_address']}")
        return rows
    (OUT / "voi.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"wrote {OUT / 'voi.json'} ({len(rows)} groups)")
    return rows


if __name__ == "__main__":
    main()
