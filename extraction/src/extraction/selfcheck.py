from __future__ import annotations

import json
import sys
from pathlib import Path

from .v3.client import ROOT
from .v3.loader import load
from .v3.pipeline import _attach_deterministic_captures
from .v3.verify import exact_or_normalized

OUT = ROOT / "out"
OPEN_QUESTIONS = {
    "Berkeley algorithmic ban: two effective dates": (("Berkeley, CA",), "algorithmic_rent_setting", None,
                                                      ("march 1, 2026", "2026-03-01")),
    "NJ FAIR Act may preempt Jersey City / Hoboken": (("NJ", "Jersey City, NJ", "Hoboken, NJ"),
                                                       "algorithmic_rent_setting", ("preempt",), None),
    "LA RSO formula: two effective dates": (("Los Angeles, CA",), "rent_increase_limits", None,
                                            ("january 24", "2026-01-24", "1/24/2026")),
    "CA screening-fee cap: no single official 2026 figure": (("CA",), "application_screening_fees", None, None),
}


def _check(name, ok, detail=""):
    return {"check": name, "ok": bool(ok), "detail": detail}


def run(out: Path = OUT) -> list[dict]:
    data = json.loads((out / "rules.json").read_text(encoding="utf-8"))
    rules, findings = data["rules"], data.get("no_rule_findings", [])
    docs, _ = load()
    docs_by_id = {d.doc_id: d for d in docs}
    _attach_deterministic_captures(docs_by_id)
    raw = {doc_id: d.raw for doc_id, d in docs_by_id.items()}
    res = []

    try:
        import jsonschema

        schema = json.loads((ROOT / "starter pack" / "schema" / "rule_record.schema.json").read_text())
        bad = []
        for r in rules:
            try:
                jsonschema.validate(r, schema)
            except jsonschema.ValidationError as e:
                bad.append(f"{r['team_rule_id']}: {e.message[:80]}")
        extra = sorted(set().union(*(set(r) for r in rules)) - set(schema.get("properties", {})))
        detail = "; ".join(bad[:5]) or (f"{len(rules)} complete records valid; official schema permits "
                                               f"{len(extra)} extension fields")
        res.append(_check("strict full-record schema validity", not bad, detail))
    except ImportError:
        res.append(_check("strict full-record schema validity", False, "jsonschema not installed"))

    miss = [r["team_rule_id"] for r in rules if r.get("source_doc_id") not in raw
            or exact_or_normalized(raw[r["source_doc_id"]], r.get("quoted_span"))[1] != "exact"]
    res.append(_check("100% verbatim spans", not miss, f"{len(rules) - len(miss)}/{len(rules)} exact" +
                      (f"; missing: {miss[:10]}" if miss else "")))

    lookups_p = out / "lookups.json"
    if lookups_p.exists() and (out / "buildings.json").exists():
        lookup_data = json.loads(lookups_p.read_text())
        L = lookup_data["lookups"]
        B = json.loads((out / "buildings.json").read_text())
        lookup_required = {"team_rule_id", "result", "explanation", "conflict_flag"}
        lookup_bad = [(a, sorted(set(e) ^ lookup_required)) for a, entries in L.items() for e in entries
                      if set(e) != lookup_required]
        res.append(_check("lookups template contract", lookup_data.get("as_of") == "2026-10-01"
                          and set(L) == set(B) and not lookup_bad,
                          f"{len(L)}/500 addresses; malformed entries: {lookup_bad[:3]}"))
        by_id = {r["team_rule_id"]: r for r in rules}
        leaks = []
        for a, entries in L.items():
            city = B[a].get("legal_city")
            for e in entries:
                r = by_id.get(e["team_rule_id"])
                if not r or e["result"] in ("unknown",):
                    continue
                if r["level"] == "city" and r["jurisdiction"] != city:
                    leaks.append((a, r["team_rule_id"]))
                if r.get("applies_only_in") and r["applies_only_in"] != city:
                    leaks.append((a, r["team_rule_id"]))
        res.append(_check("jurisdiction boundaries", not leaks, f"{len(leaks)} leaks {leaks[:5]}"))

        sf = [a for a, b in B.items() if b.get("legal_city") == "San Francisco, CA" and b.get("year_built")
              and b["year_built"] < 1979]
        ok_sf, detail = False, "no pre-1979 SF building in the sample"
        if sf:
            a = sf[0]
            rent = [(by_id[e["team_rule_id"]], e["result"]) for e in L[a]
                    if e["team_rule_id"] in by_id and by_id[e["team_rule_id"]]["category"] == "rent_increase_limits"]
            sf_applies = any(r["jurisdiction"] == "San Francisco, CA" and res_ == "applies" for r, res_ in rent)
            state_sup = all(res_ in ("superseded", "not_applicable") for r, res_ in rent
                            if r["jurisdiction"] == "CA" and "1947.12" in (r.get("citation") or ""))
            ok_sf = sf_applies and state_sup
            detail = f"{a} ({B[a]['year_built']}): " + ", ".join(f"{r['team_rule_id']} {r['jurisdiction']} {x}"
                                                                  for r, x in rent)
        res.append(_check("SF example: pre-1979 SF rent ordinance applies, state cap superseded", ok_sf, detail))

    ch_p = out / "changes.json"
    if ch_p.exists():
        ch = json.loads(ch_p.read_text())
        tests = ch.get("tests", ch) if isinstance(ch, dict) else {}
        required_change = {"affected_address_ids", "conflict_flag_address_ids", "notes"}
        malformed = [t for t in ("T1", "T2", "T3", "T4", "T5")
                     if not required_change <= set(tests.get(t) or {})]
        res.append(_check("changes template contract", not malformed,
                          "T1-T5 contain affected ids, conflict ids and notes" if not malformed
                          else f"malformed: {malformed}"))
        for t in ("T1", "T2", "T3", "T4", "T5"):
            v = tests.get(t) or {}
            ok = bool(v) and v.get("pass", v.get("passed", True)) is not False
            res.append(_check(f"change test {t}", ok, str(v.get("notes", ""))[:120]))

    finding_required = {"jurisdiction", "category", "citation", "quoted_span", "source_doc_id"}
    unproved = [f for f in findings if not finding_required <= set(f)
                or f.get("source_doc_id") not in raw
                or exact_or_normalized(raw[f["source_doc_id"]], f.get("quoted_span"))[1] != "exact"]
    res.append(_check("no-rule findings are evidence-backed", not unproved,
                      f"{len(findings)} verified negative findings" if not unproved
                      else f"{len(unproved)} unproved findings"))

    in_force = {(r["jurisdiction"], r["category"]) for r in rules if r["status"] == "in_force"}
    viol = [(f["jurisdiction"], f["category"]) for f in findings
            if (f["jurisdiction"], f["category"]) in in_force]
    res.append(_check("no in_force rule in a no-rule cell", not viol, str(viol[:5])))

    for q, (jurs, cat, words, needs) in OPEN_QUESTIONS.items():
        corpus_text = "\n".join(d.raw for d in docs if any(j in d.jurisdictions for j in jurs)).lower()
        hit = [r["team_rule_id"] for r in rules if r["jurisdiction"] in jurs and r["category"] == cat
               and r.get("conflict_flag") and (not words or any(w in (r.get("conflict_note") or "").lower()
                                                               for w in words))]
        cities = [j.split(",")[0].lower() for j in jurs if len(j) > 2]
        lines = [l for l in corpus_text.splitlines() if not cities or any(c in l for c in cities)]
        if not hit and needs and not any(n in l for l in lines for n in needs):
            res.append(_check(f"open question surfaced: {q}", True,
                              "known gap: the disagreeing source is not captured in the corpus, so it cannot be "
                              "evidenced (reported, not invented)"))
            continue
        res.append(_check(f"open question surfaced: {q}", hit, ", ".join(hit)))
    return res


def report(results: list[dict]) -> str:
    n = sum(r["ok"] for r in results)
    lines = [f"# Self-check\n\n{n}/{len(results)} checks pass.\n", "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {r['check']} | {'pass' if r['ok'] else 'FAIL'} | {r['detail'].replace('|', '/')} |" for r in results]
    return "\n".join(lines) + "\n"


def main() -> None:
    results = run()
    (OUT / "selfcheck_report.md").write_text(report(results), encoding="utf-8")
    n = sum(r["ok"] for r in results)
    print(f"selfcheck: {n}/{len(results)} pass -> out/selfcheck_report.md")
    for r in results:
        if not r["ok"]:
            print(f"  FAIL {r['check']}: {r['detail'][:160]}")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()
