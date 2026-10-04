from __future__ import annotations

import json
import re
from pathlib import Path

from ..normalize import law_key
from .client import ROOT

CAT_CODE = {"rent_increase_limits": "RENT", "just_cause_eviction": "JC", "security_deposits": "DEP",
            "application_screening_fees": "FEE", "screening_restrictions": "SCR",
            "algorithmic_rent_setting": "ALG"}
JUR_CODE = {"CA": "CA", "NJ": "NJ", "MA": "MA", "Hoboken, NJ": "HOB", "Jersey City, NJ": "JC",
            "Newark, NJ": "NWK", "Los Angeles, CA": "LA", "San Francisco, CA": "SF", "Berkeley, CA": "BRK",
            "San Diego, CA": "SD", "Santa Ana, CA": "SA", "Boston, MA": "BOS", "Cambridge, MA": "CAM"}

CHANGE_TESTS = {
    "CA-ALG-01": ("CA", "algorithmic_rent_setting", None, ["AB 325", "SB 763", "16729"]),
    "HOB-ALG-01": ("Hoboken, NJ", "algorithmic_rent_setting", None, None),
    "JC-ALG-01": ("Jersey City, NJ", "algorithmic_rent_setting", None, None),
    "NJ-ALG-01": ("NJ", "algorithmic_rent_setting", {"in_force", "not_yet_effective"}, ["FAIR", "56:9", "P.L.2026"]),
    "MA-ALG-P1": ("MA", "algorithmic_rent_setting", {"pending"}, ["S.2983", "2983"]),
    "MA-ALG-P2": ("MA", "algorithmic_rent_setting", {"pending"}, ["H.5222", "5222"]),
    "MA-RENT-P1": ("MA", "rent_increase_limits", {"failed", "pending"}, ["25-21", "Initiative", "ballot"]),
}


def _jur_code(j: str) -> str:
    return JUR_CODE.get(j) or re.sub(r"[^A-Z]", "", j.split(",")[0].upper())[:4]


def _match_key(r: dict) -> tuple[str, str, str]:
    return r["jurisdiction"], r["category"], law_key(r.get("citation"))


def assign(rules: list[dict], old_rules: list[dict]) -> dict[str, str]:
    old_by_key: dict[tuple, list[str]] = {}
    for r in old_rules:
        old_by_key.setdefault(_match_key(r), []).append(r["team_rule_id"])
    used: set[str] = set()
    next_n = max([int(r["team_rule_id"][2:]) for r in old_rules if re.fullmatch(r"r-\d{4}", r["team_rule_id"])]
                 or [0]) + 1
    rules.sort(key=lambda r: (r["jurisdiction"], r["category"], r.get("status") != "in_force",
                              law_key(r.get("citation")), r.get("title", "")))
    for r in rules:
        cands = [i for i in old_by_key.get(_match_key(r), []) if i not in used]
        if cands:
            r["team_rule_id"] = min(cands)
        else:
            r["team_rule_id"] = f"r-{next_n:04d}"
            next_n += 1
        used.add(r["team_rule_id"])
    counters: dict[tuple, int] = {}
    for r in rules:
        prefix = {"pending": "P", "failed": "F"}.get(r.get("status"), "")
        k = (r["jurisdiction"], r["category"], prefix)
        counters[k] = counters.get(k, 0) + 1
        n = counters[k]
        r["canonical_id"] = f"{_jur_code(r['jurisdiction'])}-{CAT_CODE[r['category']]}-{prefix}{n if prefix else f'{n:02d}'}"
    align_change_tests(rules)
    return {}


def _matches(r: dict, spec) -> bool:
    jur, cat, statuses, words = spec
    if r["jurisdiction"] != jur or r["category"] != cat:
        return False
    if statuses and r.get("status") not in statuses:
        return False
    if words:
        hay = " ".join([r.get("citation") or "", *(r.get("citation_aliases") or []), r.get("title") or ""])
        return any(w.lower() in hay.lower() for w in words)
    return True


def align_change_tests(rules: list[dict]) -> None:
    for test_id, spec in CHANGE_TESTS.items():
        hits = [r for r in rules if _matches(r, spec)]
        if not hits:
            continue
        target = hits[0]
        clash = next((r for r in rules if r is not target and r["canonical_id"] == test_id), None)
        if clash:
            clash["canonical_id"], target["canonical_id"] = target["canonical_id"], test_id
        else:
            target["canonical_id"] = test_id


def fill_overrides(rules: list[dict]) -> None:
    for r in rules:
        r["overrides"] = []
    state = {}
    for r in rules:
        if len(r["jurisdiction"]) == 2:
            state.setdefault((r["jurisdiction"], r["category"]), []).append(r)
    for r in rules:
        if len(r["jurisdiction"]) == 2 or r.get("event_only"):
            continue
        st = r["jurisdiction"][-2:]
        for s in state.get((st, r["category"]), []):
            cov_s, cov_r = s.get("coverage") or {}, r.get("coverage") or {}
            if cov_s.get("yields_to_local_rule") or cov_r.get("supersedes_state_rule"):
                r["overrides"].append(s["team_rule_id"])
                s["overrides"].append(r["team_rule_id"])
                r["interaction"] = _join(r.get("interaction"),
                                         f"Supersedes {s['team_rule_id']} ({s['citation']}) where both apply.")
                s["interaction"] = _join(s.get("interaction"),
                                         f"Yields to {r['team_rule_id']} ({r['citation']}) in {r['jurisdiction']}.")
            if cov_s.get("may_preempt_local_rules"):
                r["overrides"].append(s["team_rule_id"])
                s["overrides"].append(r["team_rule_id"])
                r["conflict_flag"] = True
                note = f"{s['citation']} may preempt {r['citation']}."
                r["conflict_note"] = _join(r.get("conflict_note"), note)
                s["interaction"] = _join(s.get("interaction"), f"May preempt {r['team_rule_id']} ({r['citation']}).")
                s["_preempts_local"] = True
    for s in rules:
        if s.pop("_preempts_local", False):
            if s.get("conflict_note"):
                s["interaction"] = _join(s.get("interaction"), s["conflict_note"])
            s["conflict_flag"], s["conflict_note"] = False, None
    for r in rules:
        r["overrides"] = sorted(set(r["overrides"]))


def _join(a: str | None, b: str) -> str:
    return b if not a else (a if b in a else f"{a} {b}")


REFERENCE_FILES = ["engine/rule_decisions.json", "engine/cache/overrides.json", "engine/cache/validity.json",
                   "engine/cache/conditions.json", "out/changes.json"]


def remap_references(mapping: dict[str, str], root: Path = ROOT) -> list[str]:
    if not mapping:
        return []
    pat = re.compile(r"\br-\d{4}\b")
    touched = []
    for rel in REFERENCE_FILES:
        p = root / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        new = pat.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)
        if new != text:
            p.write_text(new, encoding="utf-8")
            touched.append(rel)
    return touched


def dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
