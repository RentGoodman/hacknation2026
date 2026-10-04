import argparse
import json

from .changes import build_changes, petition_25_21_ids
from .classify_conditions import classify, classify_v6
from .explain import build_detail, publicize_lookups
from .links import current_links, links_log, load_links
from .precedence import load_annotations, summarize_log
from .prepare import prepare_rules
from .rules import ROOT, load_buildings, load_rules_meta
from .voi import compute as voi_compute
from .verdict import DEFAULT_AS_OF, lookups, precedence_context

OUT = ROOT / "out"
T5_CITIES = ("Boston, MA", "Cambridge, MA")


def assert_t5(buildings, rules, L):
    petition = petition_25_21_ids(rules)
    bad = [(a, e["team_rule_id"]) for a, entries in L.items()
           if (buildings[a]["legal_city"] or buildings[a].get("legal_city_candidate")) in T5_CITIES
           for e in entries if e["team_rule_id"] in petition]
    if bad:
        raise SystemExit(f"FAIL T5: petition 25-21 results for Boston/Cambridge addresses: {bad[:10]}")


def capture_gap_note(changes):
    if "Unmapped test rules" not in changes["T2"]["notes"]:
        return None
    import csv
    import io

    from .rules import _git_show
    local = ROOT / "corpus_extra" / "manifest_extra.csv"
    text = local.read_text() if local.exists() else _git_show("origin/main", "corpus_extra/manifest_extra.csv")
    reasons = [f"{r['doc_id']} ({r['jurisdiction']}): {r['note']}" for r in csv.DictReader(io.StringIO(text or ""))
               if r.get("capture") != "yes"]
    return ("Source text not in supplied corpus; capture attempt failed: " + " ".join(reasons)) if reasons else \
        "Source text not in supplied corpus; no capture attempt recorded."


def _manifest_extra():
    import csv
    import io

    from .rules import _git_show
    local = ROOT / "corpus_extra" / "manifest_extra.csv"
    text = local.read_text() if local.exists() else _git_show("origin/main", "corpus_extra/manifest_extra.csv")
    return list(csv.DictReader(io.StringIO(text or "")))


def t5_source_note():
    rows = [r for r in _manifest_extra() if r["doc_id"] == "DX03"]
    if rows and rows[0].get("capture") != "yes":
        return "Official decision source: capture attempt failed: " + rows[0]["note"]
    return None


def evaluation_context(fetch=False):
    from .audit_overrides import audit
    from .validity import attach
    buildings = load_buildings()
    raw_rules, meta = load_rules_meta(fetch=fetch)
    rules, prep_log = prepare_rules(raw_rules)
    load_links()
    audit_result, audit_err = audit(rules, use_api=False)
    cond_log, cond_err = classify(rules, use_api=False)
    v6_log, _ = classify_v6(rules, use_api=False)
    validity_log, _ = attach(rules, use_api=False)
    annotations, unannotated = load_annotations(rules, raw_rules)
    from .contract_fields import apply_contract_fields
    annotations, contract_disagreements = apply_contract_fields(rules, annotations)
    for r in rules:
        r["_annotation"] = None if r["team_rule_id"] in unannotated else annotations[r["team_rule_id"]]
    return {"buildings": buildings, "raw_rules": raw_rules, "rules": rules, "meta": meta, "prep_log": prep_log,
            "audit": audit_result, "audit_err": audit_err, "cond_log": cond_log, "cond_err": cond_err,
            "validity_log": validity_log, "v6_log": v6_log, "annotations": annotations,
            "unannotated": unannotated, "contract_disagreements": contract_disagreements}


def evaluation_rules(fetch=False):
    return evaluation_context(fetch=fetch)["rules"]


def presented_lookups(buildings, rules, as_of):
    details = {}
    raw = lookups(buildings, rules, as_of, details=details)
    detail = build_detail(raw, buildings, rules, details, as_of)
    return publicize_lookups(raw, detail), detail


def build_outputs(as_of, fetch=True):
    from .audit_overrides import write_report
    from .classify_conditions import heuristic_v1
    import copy
    import tempfile
    from pathlib import Path

    ctx = evaluation_context(fetch=fetch)
    buildings, raw_rules, rules, meta, prep_log = (ctx[k] for k in ("buildings", "raw_rules", "rules", "meta", "prep_log"))
    audit_result, audit_err = ctx["audit"], ctx["audit_err"]
    before_rules = copy.deepcopy(rules)
    classify(before_rules, use_api=False, fallback=heuristic_v1, use_cache=False)
    before_counts = {}
    for entries in lookups(buildings, before_rules, as_of).values():
        for e in entries:
            before_counts[e["result"]] = before_counts.get(e["result"], 0) + 1
    cond_log, cond_err = ctx["cond_log"], ctx["cond_err"]
    prec_log, details = [], {}
    L = lookups(buildings, rules, as_of, details=details, log=prec_log)
    pc = precedence_context(rules, current_links())
    if len(L) != 500 or set(L) != set(buildings):
        raise SystemExit(f"FAIL: lookups cover {len(L)} ids, expected the 500 building ids")
    assert_t5(buildings, rules, L)
    meta = {**meta, "rule_count": len(raw_rules), "rules_evaluated": len(rules)}
    changes = build_changes(buildings, rules)
    gap = capture_gap_note(changes)
    if gap:
        changes["T2"]["notes"] += " " + gap
    hour16 = OUT / "rules_hour16.json"
    if hour16.exists():
        from .ingest_new import recompute_entry
        t6 = recompute_entry(buildings, rules, hour16)
        if t6:
            changes["T6"] = t6
    t5 = t5_source_note()
    if t5:
        changes["T5"]["notes"] += " " + t5
    results = {}
    for entries in L.values():
        for e in entries:
            results[e["result"]] = results.get(e["result"], 0) + 1
    with tempfile.TemporaryDirectory() as d:
        audit_counts = write_report(rules, audit_result, Path(d) / "a.md")
        audit_md = (Path(d) / "a.md").read_text()
    classified = sum(1 for c in cond_log if not c["classifier"].startswith("heuristic"))
    run_log = {
        "as_of": as_of, **meta, **prep_log, **links_log(), "result_counts": results,
        "result_counts_with_previous_fallback": before_counts,
        "condition_classifications": cond_log,
        "condition_classifications_v6": ctx["v6_log"], "condition_classifier_error": cond_err,
        "conditions_classified_by_claude": classified, "conditions_heuristic": len(cond_log) - classified,
        "overrides_audit_counts": audit_counts, "overrides_audit_error": audit_err,
        "temporal_periods": ctx["validity_log"],
        "omitted_after_law_sunset": sorted(
            v["team_rule_id"] for v in ctx["validity_log"]
            if v.get("valid_until") and v["valid_until"] < as_of),
        "period_figures": sorted(
            v["team_rule_id"] for v in ctx["validity_log"] if v.get("figure_period_end")),
        "rules_without_annotation": ctx["unannotated"],
        "part1_annotation_disagreements": ctx["contract_disagreements"],
        "precedence_rejected_edges": pc["rejected_edges"], "precedence_rejected_pairs": pc["rejected_pairs"],
        "precedence_kept_edges": sorted([list(e) for e in pc["edges"]]),
        "precedence_actions": summarize_log(prec_log),
        "rule_decisions": json.loads((ROOT / "engine" / "rule_decisions.json").read_text()),
        "t5_check": "passed: failed petition 25-21 is absent from every Boston and Cambridge lookup; unrelated "
                    "present or future rent laws are outside this guard",
    }
    dropped = {d for r in rules for d in (x["team_rule_id"] for x in r.get("_duplicates") or [])}
    detail = build_detail(L, buildings, rules + [r for r in raw_rules if r["team_rule_id"] in dropped], details, as_of)
    public_L = publicize_lookups(L, detail)
    voi_rows = voi_compute(public_L, buildings, detail=detail)
    outs = {
        "out/lookups.json": json.dumps({"as_of": as_of, "_meta": meta, "lookups": public_L}, indent=2) + "\n",
        "out/lookups_detail.json": json.dumps(detail, indent=2) + "\n",
        "out/voi.json": json.dumps(voi_rows, indent=2) + "\n",
        "out/changes.json": json.dumps({"_meta": meta, **changes}, indent=2) + "\n",
        "out/engine_run.json": json.dumps(run_log, indent=2) + "\n",
        "out/overrides_audit.md": audit_md,
    }
    return outs, {"meta": meta, "rules": rules, "raw": raw_rules, "prep": prep_log, "L": L,
                  "public_L": public_L, "changes": changes}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=DEFAULT_AS_OF)
    ap.add_argument("--check", action="store_true",
                    help="Recompute outputs (no network, no key) and fail if they differ from the committed files")
    args = ap.parse_args(argv)
    outs, s = build_outputs(args.as_of, fetch=not args.check)
    if args.check:
        bad = [p for p, text in outs.items() if not (ROOT / p).exists() or (ROOT / p).read_text() != text]
        if bad:
            raise SystemExit(f"CHECK FAILED: outputs differ from committed files: {bad}. Run python -m engine.run and commit.")
        print(f"check passed: {len(outs)} outputs match the committed files")
        return
    for p, text in outs.items():
        (ROOT / p).write_text(text)
    meta, prep, L, changes = s["meta"], s["prep"], s["L"], s["changes"]
    warn = "  WARNING: TEST ONLY fixture rules" if meta["test_only_fixture"] else ""
    print(f"rules: {meta['rules_source']} ({len(s['raw'])} rules, {len(s['rules'])} evaluated){warn}")
    print(f"excluded {len(prep['excluded'])}, duplicate groups {len(prep['duplicates'])}, "
          f"canonical duplicates {len(prep.get('canonical_duplicates', []))}")
    print(f"wrote {', '.join(outs)} ({sum(map(len, L.values()))} lookup entries)")
    for t, v in changes.items():
        print(f"  {t}: affected {len(v['affected_address_ids'])}, conflicts {len(v.get('conflict_flag_address_ids', []))}")


if __name__ == "__main__":
    main()
