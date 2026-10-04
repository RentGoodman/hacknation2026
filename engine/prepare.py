import csv
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher

from .rules import ROOT

MANIFESTS = [ROOT / "starter pack" / "corpus" / "corpus_manifest.csv", ROOT / "corpus_extra" / "manifest_extra.csv"]
SIMILARITY = 0.9

C40P = re.compile(r"\b(c\.|ch\.|chapter)\s*40\s*P\b", re.I)


def is_ma_40p(rule):
    return (rule.get("jurisdiction") == "MA" and rule.get("category") == "rent_increase_limits"
            and bool(C40P.search(rule.get("citation") or "")))

def _cite_key(c):
    return re.sub(r"[^a-z0-9]", "", (c or "").lower())


def _norm_text(t):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (t or "").lower()).split())


def source_types():
    out = {}
    for m in MANIFESTS:
        if m.exists():
            with open(m, newline="") as f:
                for row in csv.DictReader(f):
                    out[row["doc_id"]] = row.get("source_type", "")
    return out


def same_obligation(a, b):
    if _norm_text(a.get("quoted_span")) and _norm_text(a.get("quoted_span")) == _norm_text(b.get("quoted_span")):
        return True
    return SequenceMatcher(None, _norm_text(a.get("requirement")), _norm_text(b.get("requirement"))).ratio() >= SIMILARITY


def prepare_rules(rules):
    types = source_types()
    log = {"excluded": [], "duplicates": []}
    kept = list(rules)
    groups = defaultdict(list)
    for r in kept:
        groups[(r["jurisdiction"], r["category"], _cite_key(r.get("citation")))].append(r)

    def rank(r):
        official = types.get(r.get("source_doc_id") or "", "") == "official"
        return (not official, -(r.get("confidence") or 0), r["team_rule_id"])

    out = []
    for (j, cat, _), rs in groups.items():
        clusters = []
        for r in sorted(rs, key=rank):
            for c in clusters:
                if same_obligation(c[0], r):
                    c.append(r)
                    break
            else:
                clusters.append([r])
        for c in clusters:
            out.append(c[0])
            if len(c) > 1:
                log["duplicates"].append({
                    "jurisdiction": j, "category": cat, "citation": c[0].get("citation"), "kept": c[0]["team_rule_id"],
                    "kept_source_type": types.get(c[0].get("source_doc_id") or "", "unknown"),
                    "dropped": [r["team_rule_id"] for r in c[1:]]})
    out = canonical_duplicates(out, rank, types, log)
    out = inherit_regime_coverage(out, log)
    out = attach_duplicates(out, rules, log)
    order = {r["team_rule_id"]: i for i, r in enumerate(rules)}
    return sorted(out, key=lambda r: order[r["team_rule_id"]]), log


def attach_duplicates(rules, raw, log):
    raw_by = {r["team_rule_id"]: r for r in raw}
    dups = defaultdict(list)
    for dropped, kept in sorted(log.get("remapped_references", {}).items()):
        if dropped in raw_by:
            d = raw_by[dropped]
            dups[kept].append({k: d.get(k) for k in ("team_rule_id", "title", "citation", "source_doc_id")})
    return [dict(r, _duplicates=dups[r["team_rule_id"]]) if dups.get(r["team_rule_id"]) else r for r in rules]


def canonical_duplicates(rules, rank, types, log):
    log["canonical_duplicates"] = []
    groups = defaultdict(list)
    for r in rules:
        if r.get("key_value"):
            groups[(r["jurisdiction"], r["category"], _norm_text(r["key_value"]), r.get("effective_date"))].append(r)
    drop = set()
    for (j, cat, kv, eff), rs in groups.items():
        if len(rs) < 2:
            continue
        rs = sorted(rs, key=rank)
        keep = dict(rs[0])
        sec = [f"{r['team_rule_id']} ({r.get('citation')}; {r.get('source_doc_id')}, "
               f"{types.get(r.get('source_doc_id') or '', 'unknown')})" for r in rs[1:]]
        keep["interaction"] = ((keep.get("interaction") or "") + " secondary_sources: " + "; ".join(sec) + ".").strip()
        rules = [keep if r["team_rule_id"] == keep["team_rule_id"] else r for r in rules]
        drop |= {r["team_rule_id"] for r in rs[1:]}
        log["canonical_duplicates"].append({
            "jurisdiction": j, "category": cat, "key_value": rs[0].get("key_value"), "effective_date": eff,
            "kept": keep["team_rule_id"], "kept_source_doc_id": keep.get("source_doc_id"),
            "secondary_sources": [r["team_rule_id"] for r in rs[1:]]})
    remap = {s: e["kept"] for e in log["canonical_duplicates"] for s in e["secondary_sources"]}
    remap.update({x: e["kept"] for e in log.get("duplicates", []) for x in e["dropped"]})
    out = []
    for r in rules:
        if r["team_rule_id"] in drop:
            continue
        ov = r.get("overrides") or []
        new_ov = sorted({remap.get(o, o) for o in ov} - {r["team_rule_id"]})
        if new_ov != sorted(ov):
            r = dict(r, overrides=new_ov)
            text = r.get("interaction") or ""
            for old, kept_id in remap.items():
                text = text.replace(old, kept_id)
            r["interaction"] = text
        out.append(r)
    log["remapped_references"] = remap
    return out


DECISIVE = ("built_on_or_before", "built_after", "min_building_age_years", "min_units", "max_units")
REGIME_CATEGORIES = ("rent_increase_limits",)


def _decisive(r):
    c = r.get("coverage_conditions")
    if not isinstance(c, dict):
        return None
    d = {k: c.get(k) for k in DECISIVE if c.get(k) is not None}
    if not d:
        return None
    return {**d, "construction_date_basis": c.get("construction_date_basis")}


def inherit_regime_coverage(rules, log):
    log["regime_inheritance"] = []
    groups = defaultdict(list)
    for r in rules:
        if r.get("level") == "city" and r["category"] in REGIME_CATEGORIES:
            groups[(r["jurisdiction"], r["category"])].append(r)
    replace = {}
    for (j, cat), rs in sorted(groups.items()):
        regimes = sorted((r for r in rs if _decisive(r)), key=lambda r: r["team_rule_id"])
        if not regimes:
            continue
        covs = {json.dumps(_decisive(r), sort_keys=True) for r in regimes}
        heirs = sorted((r for r in rs if not _decisive(r)), key=lambda r: r["team_rule_id"])
        if len(covs) > 1:
            for h in heirs:
                log["regime_inheritance"].append({"team_rule_id": h["team_rule_id"], "jurisdiction": j, "category": cat,
                                                  "inherited_from": None, "reason": "regime rules disagree on coverage"})
            continue
        src = _decisive(regimes[0])
        for h in heirs:
            own = h.get("coverage_conditions") if isinstance(h.get("coverage_conditions"), dict) else \
                {"summary": h.get("coverage_conditions"), "owner_conditions": None, "other_conditions": None}
            new = dict(h)
            new["coverage_conditions"] = {**own, **src}
            new["_inherited_from"] = [r["team_rule_id"] for r in regimes]
            replace[h["team_rule_id"]] = new
            log["regime_inheritance"].append({"team_rule_id": h["team_rule_id"], "jurisdiction": j, "category": cat,
                                              "inherited_from": new["_inherited_from"], "coverage": src})
    return [replace.get(r["team_rule_id"], r) for r in rules]
