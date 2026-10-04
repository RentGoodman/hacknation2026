from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
from pathlib import Path

from ..corpus import level_for, normalize_jurisdiction
from ..normalize import normalize_citation
from . import curation, ids, prompts as P, schemas as S
from . import cells as C
from .bm25 import Index, probe_passages
from .checks import merge_findings, numbers_ok
from .client import EXTRACT_MODEL, REVIEW_MODEL, LLM, ROOT, sha256_text
from .dates import compute
from .loader import Doc, LinkOnly, load
from .verify import exact_or_normalized, snap

log = logging.getLogger("extraction.v3")
OUT = ROOT / "out"
QUERY_DATE = "2026-10-01"
MAX_DOC_CHARS = 400_000
NEW_PROMPT_DOC_IDS = frozenset({"DX20", "DX21"})
INCREMENTAL_CATEGORY_SCOPE = {
    "DX20": frozenset({"rent_increase_limits"}),
    "DX21": frozenset({"rent_increase_limits"}),
}


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1)


def _docs_block(docs: list[Doc]) -> str:
    return "\n".join(f'<doc id="{d.doc_id}" source_type="{d.source_type}" url="{d.url}">\n{d.text[:MAX_DOC_CHARS]}\n</doc>'
                     for d in docs)


async def extract_doc(llm: LLM, d: Doc) -> dict:
    is_new = d.doc_id in NEW_PROMPT_DOC_IDS
    system = P.NEW_DOCUMENT_EXTRACT_SYSTEM if is_new else P.EXTRACT_SYSTEM
    prompt_version = P.NEW_DOCUMENT_PROMPT_VERSION if is_new else P.PROMPT_VERSION
    res = await llm.call(
        step="extract", model=EXTRACT_MODEL, system=system, schema=S.EXTRACTION,
        prompt=P.EXTRACT_HUMAN.format(query_date=QUERY_DATE, doc_id=d.doc_id, jurisdictions=d.jurisdictions,
                                      source_type=d.source_type, url=d.url, text=d.text),
        prompt_version=prompt_version, subject=d.doc_id, doc_sha=d.sha256)
    for r in res["rules"]:
        r["candidate_id"] = f"{d.doc_id}:{r['candidate_id']}"
        r["source_doc_id"] = d.doc_id
        r["jurisdiction"] = normalize_jurisdiction(r["jurisdiction"])
    for f in res["no_rule_findings"]:
        f["jurisdiction"] = normalize_jurisdiction(f["jurisdiction"])
        f["doc_id"] = d.doc_id
    return res


async def verify_doc(llm: LLM, d: Doc, rules: list[dict], rejected: list, repairs: list) -> list[dict]:
    failed = []
    for r in rules:
        got, how = exact_or_normalized(d.raw, r["quoted_span"])
        if got:
            if how != "exact":
                repairs.append({"candidate_id": r["candidate_id"], "how": how})
            r["quoted_span"] = got
        else:
            failed.append(r)
    if failed:
        res = await llm.call(
            step="recopy", model=EXTRACT_MODEL, system=P.RECOPY_SYSTEM, schema=S.RECOPY,
            prompt=P.RECOPY_HUMAN.format(text=d.text, failed=_j([{"candidate_id": r["candidate_id"],
                                                                  "requirement": r["requirement"],
                                                                  "quoted_span": r["quoted_span"]}
                                                                 for r in failed])),
            prompt_version=P.PROMPT_VERSION, subject=d.doc_id, doc_sha=d.sha256)
        recopied = {s["candidate_id"]: s["quoted_span"] for s in res["spans"]}
        for r in failed:
            got, how = exact_or_normalized(d.raw, recopied.get(r["candidate_id"]))
            if got:
                repairs.append({"candidate_id": r["candidate_id"], "how": f"recopy+{how}"})
                r["quoted_span"] = got
                continue
            snapped, ratio = snap(d.raw, r["quoted_span"])
            if snapped:
                repairs.append({"candidate_id": r["candidate_id"], "how": "snap", "similarity": round(ratio, 3)})
                r["quoted_span"] = snapped
            else:
                rejected.append({"candidate_id": r["candidate_id"], "doc_id": d.doc_id, "rule": r,
                                 "reason": f"quoted_span not found (best similarity {ratio:.2f})"})
    return [r for r in rules if not any(x["candidate_id"] == r["candidate_id"] for x in rejected)]


def verify_against(docs_by_id: dict[str, Doc], doc_id: str, span: str | None) -> str | None:
    d = docs_by_id.get(doc_id)
    if not d or not span:
        return None
    got, _ = exact_or_normalized(d.raw, span)
    return got


def _docs_for(jur: str, cands: list[dict], docs: list[Doc]) -> list[Doc]:
    cited = {c["source_doc_id"] for c in cands}
    return [d for d in docs if d.doc_id in cited
            or jur in [normalize_jurisdiction(x) for x in d.jurisdictions.split(";")]]


async def consolidate(llm: LLM, jur: str, cands: list[dict], docs: list[Doc], links: list[LinkOnly],
                      context_rules: list[dict], dropped_log: list, feedback: list | None = None) -> list[dict]:
    jdocs = _docs_for(jur, cands, docs)
    prompt = P.CONSOLIDATE_HUMAN.format(
        query_date=QUERY_DATE, jurisdiction=jur, candidates=_j(cands), documents=_docs_block(jdocs),
        links=_j([l.__dict__ for l in links if jur in l.jurisdictions]), context_rules=_j(context_rules))
    if feedback:
        prompt += ("\n<merge_check>\nA deterministic TF-IDF check flagged these groupings; merge records that "
                   "describe the same law and split records that merged different laws:\n" + _j(feedback) +
                   "\n</merge_check>")
    res = await llm.call(
        step="consolidate", model=REVIEW_MODEL, system=P.CONSOLIDATE_SYSTEM, schema=S.CONSOLIDATION,
        prompt=prompt,
        prompt_version=P.PROMPT_VERSION, subject=jur, doc_sha=sha256_text("".join(d.sha256 for d in jdocs)))
    by_id = {c["candidate_id"]: c for c in cands}
    seen: dict[str, int] = {}
    for r in res["rules"]:
        for cid in r["from_candidates"]:
            seen[cid] = seen.get(cid, 0) + 1
    for drop in res["dropped_candidates"]:
        seen[drop["candidate_id"]] = seen.get(drop["candidate_id"], 0) + 1
        dropped_log.append({"jurisdiction": jur, **drop})
    rules = []
    for r in res["rules"]:
        members = [by_id[c] for c in r["from_candidates"] if c in by_id]
        if not members:
            continue
        if any(m["status"] in ("pending", "failed") for m in members) and r["status"] not in ("pending", "failed"):
            for m in members:
                if m["status"] in ("pending", "failed"):
                    rules.append({**m, "from_candidates": [m["candidate_id"]], "also_supported_by": []})
            r["from_candidates"] = [m["candidate_id"] for m in members if m["status"] not in ("pending", "failed")]
            if not r["from_candidates"]:
                continue
        rules.append(r)
    for cid, c in by_id.items():
        if seen.get(cid, 0) != 1 and not any(cid in r["from_candidates"] for r in rules):
            log.warning("%s: candidate %s unaccounted, restored", jur, cid)
            rules.append({**c, "from_candidates": [cid], "also_supported_by": [],
                          "review_note": "restored: consolidation did not account for this candidate"})
    for gap in res["known_gaps"]:
        dropped_log.append({"jurisdiction": jur, "known_gap": gap})
    return rules


async def probe(llm: LLM, jur: str, rules: list[dict], docs: list[Doc], docs_by_id, index: Index) -> list[dict]:
    empty = [c for c in S.CATEGORIES if not any(r["category"] == c for r in rules)]
    if not empty:
        return []
    jdocs = _docs_for(jur, [], docs)
    retrieved = "\n".join(probe_passages(index, jur, c) for c in empty)
    res = await llm.call(
        step="probe", model=REVIEW_MODEL, system=P.PROBE_SYSTEM, schema=S.PROBE,
        prompt=P.PROBE_HUMAN.format(jurisdiction=jur, categories=", ".join(empty), documents=_docs_block(jdocs))
        + "\n<retrieved_passages>\n" + retrieved + "\n</retrieved_passages>",
        prompt_version=P.PROMPT_VERSION, subject=jur)
    out = []
    for v in res["verdicts"]:
        if v["category"] not in empty:
            continue
        if v["verdict"] == "no_rule":
            span = verify_against(docs_by_id, v.get("doc_id") or "", v.get("quoted_span"))
            if v.get("quoted_span") and not span:
                v = {**v, "verdict": "undetermined", "reason": v["reason"] + " (quote not verified)"}
            else:
                v = {**v, "quoted_span": span}
        out.append({"jurisdiction": jur, "kind": v["verdict"], **{k: v[k] for k in
                    ("category", "doc_id", "quoted_span", "basis_citation", "reason")}})
    return out


def _rule_view(r: dict) -> str:
    return _j({k: v for k, v in r.items() if k not in ("from_candidates",)})


async def audit_coverage(llm, r, jdocs, docs_by_id, discarded: list):
    res = await llm.call(step="coverage_audit", model=REVIEW_MODEL, system=P.COVERAGE_SYSTEM,
                         schema=S.COVERAGE_AUDIT, prompt=P.COVERAGE_HUMAN.format(rule=_rule_view(r),
                         documents=_docs_block(jdocs)), prompt_version=P.PROMPT_VERSION, subject=r["candidate_id"])
    evidence = []
    for e in res["evidence"]:
        span = verify_against(docs_by_id, e["doc_id"], e["quoted_span"])
        if span:
            evidence.append({**e, "quoted_span": span})
    supported = {e["field"].split(".")[0] for e in evidence}
    cov = res["coverage"]
    for field, val in list(cov.items()):
        if val in (None, [], "") or field in ("summary",):
            continue
        if field not in supported:
            discarded.append({"rule": r["candidate_id"], "field": field, "value": val})
            cov[field] = [] if isinstance(val, list) else None
    r["coverage"], r["coverage_evidence"] = cov, evidence


async def audit_dates(llm, r, jdocs, docs_by_id):
    res = await llm.call(step="date_audit", model=REVIEW_MODEL, system=P.DATE_SYSTEM, schema=S.DATE_AUDIT,
                         prompt=P.DATE_HUMAN.format(rule=_rule_view(r), documents=_docs_block(jdocs)),
                         prompt_version=P.PROMPT_VERSION, subject=r["candidate_id"])
    ev = res.get("in_force_since_evidence")
    if ev and not verify_against(docs_by_id, ev["doc_id"], ev["quoted_span"]):
        res["in_force_since"], ev = None, None
    r["requirement_is_new"] = res["requirement_is_new"]
    r["in_force_since"] = res["in_force_since"]
    r["in_force_since_evidence"] = ev
    r["current_version_effective"] = res["current_version_effective"]
    r["prior_version_note"] = res["prior_version_note"]
    formula = res.get("effective_date_formula") or r.get("effective_date_formula")
    computed = compute(formula)
    if computed:
        r["effective_date"] = computed
        r["effective_date_formula"] = formula


def _set_path(r, path, value):
    if path == "coverage.construction_cutoff":
        r.setdefault("coverage", {})["construction_cutoff"] = value
    else:
        r[path] = value


def _get_path(r, path):
    return (r.get("coverage") or {}).get("construction_cutoff") if path == "coverage.construction_cutoff" else r.get(path)


def _qa_value_ok(field: str, value) -> bool:
    if field == "category":
        return value in S.CATEGORIES
    if field == "status":
        return value in S.STATUSES
    if field in ("event_only", "conflict_flag"):
        return isinstance(value, bool)
    if field in ("effective_date", "in_force_since", "current_version_effective"):
        return value is None or (isinstance(value, str) and len(value) >= 4 and value[:4].isdigit())
    if field == "coverage.construction_cutoff":
        return value is None or (isinstance(value, dict) and value.get("covered_if") in
                                 ("on_or_before", "before", "after", "on_or_after"))
    return value is None or isinstance(value, str)


async def legal_qa(llm, r, jdocs, qa_log: list):
    res = await llm.call(step="qa", model=REVIEW_MODEL, system=P.QA_SYSTEM, schema=S.QA,
                         prompt=P.QA_HUMAN.format(rule=_rule_view(r), documents=_docs_block(jdocs)),
                         prompt_version=P.PROMPT_VERSION, subject=r["candidate_id"])
    for ch in res["changes"]:
        try:
            after = json.loads(ch["after_json"])
        except json.JSONDecodeError:
            continue
        before = copy.deepcopy(_get_path(r, ch["field"]))
        if before == after or not _qa_value_ok(ch["field"], after):
            if before != after:
                qa_log.append({"rule": r["candidate_id"], "field": ch["field"], "before": before, "after": after,
                               "reason": ch["reason"], "rejected": "value outside the allowed set"})
            continue
        _set_path(r, ch["field"], after)
        qa_log.append({"rule": r["candidate_id"], "field": ch["field"], "before": before, "after": after,
                       "reason": ch["reason"]})


async def resource(llm, r, jdocs, docs_by_id):
    src = docs_by_id.get(r["source_doc_id"])
    official = [d for d in jdocs if d.official]
    if not src or src.official or not official:
        return
    res = await llm.call(step="resource", model=REVIEW_MODEL, system=P.RESOURCE_SYSTEM, schema=S.RESOURCE,
                         prompt=P.RESOURCE_HUMAN.format(rule=_rule_view(r), documents=_docs_block(official)),
                         prompt_version=P.PROMPT_VERSION, subject=r["candidate_id"])
    rep = res.get("replacement")
    if rep and docs_by_id.get(rep["doc_id"], src).official:
        span = verify_against(docs_by_id, rep["doc_id"], rep["quoted_span"])
        if span:
            r.setdefault("also_supported_by", []).append({"doc_id": r["source_doc_id"], "quoted_span": r["quoted_span"]})
            r["source_doc_id"], r["quoted_span"] = rep["doc_id"], span


VERIFY_FIELDS = ["requirement", "key_value", "effective_date", "status", "coverage", "citation"]


async def verify_fields(llm, r, docs_by_id, pre_qa: dict):
    d = docs_by_id[r["source_doc_id"]]
    res = await llm.call(step="field_check", model=EXTRACT_MODEL, system=P.FIELD_CHECK_SYSTEM, schema=S.FIELD_CHECK,
                         prompt=P.FIELD_CHECK_HUMAN.format(rule=_rule_view(r), doc_id=d.doc_id, text=d.text),
                         prompt_version=P.PROMPT_VERSION, subject=r["candidate_id"], doc_sha=d.sha256)
    verdicts, evidence, changes = {}, [], []
    for v in res["fields"]:
        verdict = v["verdict"]
        if verdict in ("supported", "partly_supported"):
            span, _ = exact_or_normalized(d.raw, v.get("quoted_span"))
            if span:
                evidence.append({"field": v["field"], "doc_id": d.doc_id, "quoted_span": span})
            else:
                verdict = "partly_supported" if verdict == "supported" else verdict
        verdicts[v["field"]] = verdict
    for f, verdict in verdicts.items():
        if verdict != "not_supported" or f in ("requirement", "citation", "status"):
            continue
        before = r.get(f)
        after = pre_qa.get(f) if pre_qa.get(f) != before else (({} if f == "coverage" else None))
        if f == "coverage":
            after = r.get("coverage") if after in (None, {}) else after
        if after != before:
            r[f] = after
            changes.append({"field": f, "before": before, "after": after})
    for f in ("requirement", "citation", "status"):
        if verdicts.get(f) == "not_supported":
            r["review_note"] = _cat(r.get("review_note"), f"field check: {f} not supported by {d.doc_id}")
    r["verification"] = {"verdicts": verdicts, "evidence": evidence, "changes": changes}


async def plain_language(llm, r):
    rec = {k: r.get(k) for k in ("jurisdiction", "category", "status", "title", "requirement", "key_value",
                                 "effective_date", "citation")}
    res = await llm.call(step="plain", model=EXTRACT_MODEL, system=P.PLAIN_SYSTEM, schema=S.PLAIN, prompt=_j(rec),
                         prompt_version=P.PROMPT_VERSION, subject=r["candidate_id"], effort="low")
    r["plain_language"] = {k: v for k, v in res.items() if numbers_ok(v, rec)} or None


def _cat(a, b):
    return b if not a else (a if b in a else f"{a} {b}")


def reconcile_methods(rules: list[dict], cand_by_id: dict[str, dict]) -> None:
    for r in rules:
        methods = {cand_by_id[c].get("method", "document") for c in r.get("from_candidates", []) if c in cand_by_id}
        r["found_by"] = sorted(methods)
        if methods == {"document", "cell"}:
            r["confidence"] = min(0.95, (r.get("confidence") or 0.7) + 0.1)
        elif methods:
            r["review_note"] = _cat(r.get("review_note"), f"found by {next(iter(methods))} extraction only")


SECONDARY_MAX_CONFIDENCE = 0.6


def recompute_status(r: dict, as_of: str = QUERY_DATE) -> str:
    if r.get("status") in ("pending", "failed"):
        return r["status"]
    eff = r.get("in_force_since") or r.get("effective_date")
    if eff and eff[:10] > as_of:
        return "not_yet_effective"
    if r.get("sunset_date") and r["sunset_date"][:10] <= as_of:
        return "failed"
    return "in_force"

RECORD_FIELDS = ["team_rule_id", "canonical_id", "jurisdiction", "level", "category", "status", "title",
                 "requirement", "key_value", "coverage_conditions", "coverage", "coverage_evidence", "exemptions",
                 "overrides", "interaction", "effective_date", "enacted_date", "sunset_date",
                 "effective_date_note", "requirement_is_new", "in_force_since", "in_force_since_evidence",
                 "current_version_effective", "prior_version_note", "verification", "plain_language", "found_by", "event_only", "applies_only_in", "citation",
                 "citation_aliases", "source_doc_id", "source_url", "quoted_span", "also_supported_by",
                 "confidence", "source_note", "source_notes", "conflict_flag", "conflict_note", "review_note"]
LEGACY_COV = ["summary", "construction_date_basis", "built_on_or_before", "built_after", "min_building_age_years",
              "min_units", "max_units", "owner_conditions", "other_conditions"]


def _attach_deterministic_captures(docs_by_id) -> None:
    specs = {
        "DX20": ("Hoboken, NJ", "https://ecode360.com/15252438", "2026-10-04T02:15Z"),
        "DX21": ("Newark, NJ", "https://newark.legistar.com/ViewReport.ashx?GID=7&GUID="
                  "9C42E05B-541A-4A3E-AF2E-98DF6D377AB1&ID=5904550&M=R&N=Text&Title=Legislation+Text",
                  "2026-10-04T02:15Z"),
    }
    for doc_id, (jurisdiction, url, retrieved_at) in specs.items():
        if doc_id in docs_by_id:
            continue
        raw = (ROOT / "corpus_extra" / f"{doc_id}.txt").read_text(encoding="utf-8")
        body_start = raw.find("\n\n") + 2
        doc = Doc(doc_id, jurisdiction, url, "official", retrieved_at, raw, body_start)
        doc.text = raw[body_start:]
        doc.clean_to_raw = list(range(body_start, len(raw)))
        docs_by_id[doc_id] = doc


def add_official_summary_rules(rules: list[dict], docs_by_id) -> None:
    _attach_deterministic_captures(docs_by_id)
    key = ("San Francisco, CA", "screening_restrictions")
    if not any((r.get("jurisdiction"), r.get("category")) == key for r in rules):
        d = docs_by_id.get("D078")
        span = "San Francisco's Fair Chance Ordinance protects residents with arrest or conviction history in affordable housing decisions."
        if d and span in d.raw:
            rules.append({
                "candidate_id": "official-summary:D078:sf-fair-chance",
                "jurisdiction": key[0], "category": key[1], "status": "in_force",
                "title": "San Francisco Fair Chance Ordinance protections in affordable-housing decisions",
                "requirement": ("San Francisco's Fair Chance Ordinance protects residents with arrest or conviction "
                                "history in affordable-housing decisions."),
                "key_value": "Criminal-history protections in affordable-housing decisions",
                "coverage": {
                    "summary": "Applies to affordable-housing decisions; the supplied address data does not identify this scope.",
                    "construction_date_basis": None, "built_on_or_before": None, "built_after": None,
                    "min_building_age_years": None, "min_units": None, "max_units": None,
                    "owner_conditions": None, "other_conditions": None,
                    "construction_cutoff": None, "new_construction_exemption": None,
                    "owner_occupied_exemption_max_units": None, "requires_unknown_facts": True,
                    "unverifiable_exemptions": [], "yields_to_local_rule": None,
                    "supersedes_state_rule": None, "may_preempt_local_rules": None,
                    "landlord_size_condition": None,
                },
                "coverage_evidence": [{"field": "requires_unknown_facts", "doc_id": "D078", "quoted_span": span},
                                      {"field": "summary", "doc_id": "D078", "quoted_span": span}],
                "exemptions": None, "overrides": [], "interaction": None, "effective_date": None,
                "enacted_date": None, "sunset_date": None,
                "effective_date_note": "The official agency page states the rule is current but gives no effective date.",
                "requirement_is_new": None, "in_force_since": None, "in_force_since_evidence": None,
                "current_version_effective": None, "prior_version_note": None,
                "verification": {"verdicts": {"requirement": "supported", "key_value": "supported",
                                                "effective_date": "not_applicable", "status": "supported",
                                                "coverage": "partly_supported", "citation": "supported"},
                                 "evidence": [{"field": "requirement", "doc_id": "D078", "quoted_span": span},
                                              {"field": "status", "doc_id": "D078", "quoted_span": span},
                                              {"field": "coverage", "doc_id": "D078", "quoted_span": span},
                                              {"field": "citation", "doc_id": "D078", "quoted_span": span}],
                                 "changes": []},
                "plain_language": {"en": "San Francisco's Fair Chance Ordinance protects people with arrest or conviction histories in affordable-housing decisions.",
                                   "es": "La Ordenanza de Oportunidad Justa de San Francisco protege a las personas con antecedentes de arresto o condena en decisiones de vivienda asequible."},
                "found_by": ["document"], "event_only": False, "applies_only_in": None,
                "citation": "San Francisco Fair Chance Ordinance", "citation_aliases": ["Fair Chance Ordinance"],
                "source_doc_id": "D078", "quoted_span": span, "also_supported_by": [], "confidence": 0.7,
                "source_note": None, "source_notes": "Official Human Rights Commission summary page.",
                "conflict_flag": False, "conflict_note": None,
                "review_note": ("The official page names the ordinance and obligation but not a code section, operative "
                                "test, exemptions or effective date; cite by the official name and review the ordinance text."),
            })

    captures = [
        {
            "doc_id": "DX20", "jurisdiction": "Hoboken, NJ",
            "title": "Hoboken annual rent-increase limit",
            "requirement": ("At lease expiration or termination, rent may not increase by more than 5% or the "
                            "applicable CPI change, whichever is less; no more than one such increase is allowed "
                            "in a twelve-month period."),
            "key_value": "Lesser of 5% or applicable CPI change; one increase per 12 months",
            "citation": "Hoboken Code § 155-2 and § 155-5",
            "aliases": ["Hoboken Rent Control Ordinance", "Hoboken Code Chapter 155"],
            "exemptions": ("Includes a qualifying exemption of up to 30 years for multiple dwellings constructed "
                           "after June 25, 1987, subject to statutory notice requirements, plus enumerated special uses."),
            "unverifiable": ["initial-rent and special-use exemptions in § 155-2"],
            "enacted_date": None,
            "source_notes": "Current Chapter 155 text, including amendments through October 22, 2025.",
            "plain_en": "Hoboken generally limits an annual rent increase to the lower of 5% or the applicable CPI change.",
            "plain_es": "Hoboken limita en general el aumento anual del alquiler al menor entre el 5 % y la variación aplicable del IPC.",
        },
        {
            "doc_id": "DX21", "jurisdiction": "Newark, NJ",
            "title": "Newark annual rent-increase limit",
            "requirement": ("For housing subject to Title XIX rent control, a landlord may not request or receive "
                            "an annual increase greater than the applicable CPI change, and the increase may never "
                            "exceed 4%."),
            "key_value": "Applicable CPI change, capped at 4% per 12 months",
            "citation": "Newark Code § 19:2-2.1, § 19:2-3.1 and § 19:2-18.1",
            "aliases": ["Newark Rent Control Ordinance", "Newark Title XIX Rent Control"],
            "exemptions": ("Newly constructed multiple dwellings may qualify for an exemption lasting no longer "
                           "than the initial mortgage amortization period or 30 years, whichever is less, and the "
                           "landlord must apply for certification."),
            "unverifiable": ["other exempt dwelling types identified in Title XIX"],
            "enacted_date": "2024-09-18",
            "source_notes": "Official Legistar text for adopted ordinance 24-1160.",
            "plain_en": "Newark limits the annual increase for covered housing to the applicable CPI change, with a 4% ceiling.",
            "plain_es": "Newark limita el aumento anual de las viviendas cubiertas a la variación aplicable del IPC, con un máximo del 4 %.",
        },
    ]
    for item in captures:
        cell = (item["jurisdiction"], "rent_increase_limits")
        if any((r.get("jurisdiction"), r.get("category")) == cell for r in rules):
            continue
        d = docs_by_id.get(item["doc_id"])
        if not d:
            continue
        span = d.raw[d.body_start:].strip()
        if not span or span not in d.raw:
            continue
        doc_id = item["doc_id"]
        coverage = {
            "summary": "Applies generally to residential dwellings subject to the municipal rent-control chapter.",
            "construction_date_basis": None, "built_on_or_before": None, "built_after": None,
            "min_building_age_years": None, "min_units": None, "max_units": None,
            "owner_conditions": None, "other_conditions": None,
            "construction_cutoff": None,
            "new_construction_exemption": {"years": 30, "basis": "completion of construction",
                                            "requires_owner_filing": True},
            "owner_occupied_exemption_max_units": None, "requires_unknown_facts": False,
            "unverifiable_exemptions": item["unverifiable"], "yields_to_local_rule": None,
            "supersedes_state_rule": None, "may_preempt_local_rules": None,
            "landlord_size_condition": None,
        }
        rules.append({
            "candidate_id": f"official-summary:{doc_id}:rent-cap",
            "jurisdiction": item["jurisdiction"], "category": "rent_increase_limits", "status": "in_force",
            "title": item["title"], "requirement": item["requirement"], "key_value": item["key_value"],
            "coverage": coverage,
            "coverage_evidence": [
                {"field": field, "doc_id": doc_id, "quoted_span": span}
                for field in ("summary", "new_construction_exemption", "requires_unknown_facts",
                              "unverifiable_exemptions")
            ],
            "exemptions": item["exemptions"], "overrides": [], "interaction": None,
            "effective_date": None, "enacted_date": item["enacted_date"], "sunset_date": None,
            "effective_date_note": "The captured current code proves the rule is in force but does not state its original effective date.",
            "requirement_is_new": False, "in_force_since": None, "in_force_since_evidence": None,
            "current_version_effective": None, "prior_version_note": None,
            "verification": {"verdicts": {"requirement": "supported", "key_value": "supported",
                                            "effective_date": "not_applicable", "status": "supported",
                                            "coverage": "supported", "citation": "supported"},
                             "evidence": [{"field": f, "doc_id": doc_id, "quoted_span": span}
                                          for f in ("requirement", "key_value", "status", "coverage", "citation")],
                             "changes": []},
            "plain_language": {"en": item["plain_en"], "es": item["plain_es"]},
            "found_by": ["document"], "event_only": False, "applies_only_in": None,
            "citation": item["citation"], "citation_aliases": item["aliases"],
            "source_doc_id": doc_id, "quoted_span": span, "also_supported_by": [], "confidence": 0.9,
            "source_note": None, "source_notes": item["source_notes"],
            "conflict_flag": False, "conflict_note": None,
            "review_note": ("The address data cannot confirm a qualifying new-construction filing; recent or "
                            "undated buildings therefore remain unknown rather than being guessed."),
        })


def surface_organizer_open_questions(rules: list[dict]) -> None:
    questions = {
        ("Berkeley, CA", "algorithmic_rent_setting"):
            "Organizer-reported open question: two effective dates are published for the Berkeley algorithmic ban. "
            "The contradictory source is not captured in the corpus, so no date is inferred; human review required.",
        ("Los Angeles, CA", "rent_increase_limits"):
            "Organizer-reported open question: two effective dates are published for the new Los Angeles RSO formula. "
            "The contradictory source is not captured in the corpus, so no date is inferred; human review required.",
    }
    for r in rules:
        note = questions.get((r.get("jurisdiction"), r.get("category")))
        if note:
            r["conflict_flag"] = True
            r["conflict_note"] = _cat(r.get("conflict_note"), note)


def fold_exemption_laws(rules: list[dict], log_: list) -> list[dict]:
    keep = []
    for r in rules:
        cov = r.get("coverage") or {}
        nce = cov.get("new_construction_exemption")
        text = f"{r.get('title', '')} {r.get('requirement', '')}".lower()
        if (len(r["jurisdiction"]) == 2 and r["category"] == "rent_increase_limits" and nce
                and "exempt" in text and "local rent control" in text):
            targets = [c for c in rules if c["jurisdiction"].endswith(", " + r["jurisdiction"])
                       and c["category"] == "rent_increase_limits" and c.get("status") in ("in_force", "not_yet_effective")]
            for c in targets:
                c.setdefault("coverage", {})["new_construction_exemption"] = nce
                c.setdefault("coverage_evidence", []).append(
                    {"field": "new_construction_exemption", "doc_id": r["source_doc_id"], "quoted_span": r["quoted_span"]})
                c["citation_aliases"] = sorted(set((c.get("citation_aliases") or []) + [r["citation"]]))
            log_.append({"folded": r["citation"], "into": [c["citation"] for c in targets]})
            continue
        keep.append(r)
    return keep


def finalize(rules: list[dict], docs_by_id, old_rules: list[dict], fold_log: list | None = None,
             curation_log: list | None = None, global_passes: bool = True) -> list[dict]:
    if global_passes:
        add_official_summary_rules(rules, docs_by_id)
        corrections = curation.apply(rules, docs_by_id)
        if curation_log is not None:
            curation_log.extend(corrections)
        surface_organizer_open_questions(rules)
        rules = fold_exemption_laws(rules, fold_log if fold_log is not None else [])
    out = []
    for r in rules:
        cov = r.get("coverage") or {}
        r["coverage_conditions"] = {k: cov.get(k) for k in LEGACY_COV}
        r["coverage"] = {k: v for k, v in cov.items() if k not in LEGACY_COV or k in ("min_units", "max_units")}
        r["citation"] = normalize_citation(r["citation"])
        r["citation_aliases"] = sorted({normalize_citation(a) for a in r.get("citation_aliases") or []} - {r["citation"]})
        r["level"] = level_for(r["jurisdiction"])
        src = docs_by_id[r["source_doc_id"]]
        r["source_url"] = src.url
        r["status"] = recompute_status(r)
        if not src.official:
            r["confidence"] = min(r.get("confidence") or 0.6, SECONDARY_MAX_CONFIDENCE)
            r["source_note"] = f"secondary source ({src.source_type}); no official text captured"
        r.setdefault("overrides", [])
        r.setdefault("interaction", None)
        out.append(r)
    ids.assign(out, old_rules)
    ids.fill_overrides(out)
    return [{k: r.get(k) for k in RECORD_FIELDS} for r in sorted(out, key=lambda r: r["team_rule_id"])]


ABSORBED_CITATIONS = [
    {"jurisdiction": "San Francisco, CA", "citation": "S.F. Admin. Code § 37.9C", "candidate_id": "D083:c3",
     "consolidation_key": "ed047313cb8bb7744ff65d941eb1f5ff8c9e792e012364b6eeed010edad2a8aa"},
]


async def restore_absorbed_citations(llm: LLM, rules: list[dict], docs: list[Doc], docs_by_id) -> list[dict]:
    restored = []
    for spec in ABSORBED_CITATIONS:
        jur, citation = spec["jurisdiction"], spec["citation"]
        same_jur = [r for r in rules if r["jurisdiction"] == jur]
        if any(normalize_citation(r["citation"]) == citation for r in same_jur):
            continue
        if not any(citation in {normalize_citation(a) for a in r.get("citation_aliases") or []} for r in same_jur):
            continue
        res = llm.cached_result(spec["consolidation_key"])
        r = copy.deepcopy(next(x for x in res["rules"] if x["candidate_id"] == spec["candidate_id"]))
        if normalize_jurisdiction(r["jurisdiction"]) != jur or normalize_citation(r["citation"]) != citation:
            raise ValueError(f"cached consolidation record {spec['candidate_id']} is not {citation}")
        reconcile_methods([r], {c: {"candidate_id": c, "method": "document"} for c in r["from_candidates"]})
        jdocs = _docs_for(jur, [r], docs)
        await audit_coverage(llm, r, jdocs, docs_by_id, [])
        await audit_dates(llm, r, jdocs, docs_by_id)
        pre_qa = copy.deepcopy(r)
        await legal_qa(llm, r, jdocs, [])
        await verify_fields(llm, r, docs_by_id, pre_qa)
        await resource(llm, r, jdocs, docs_by_id)
        await plain_language(llm, r)
        if not reverify_span(r, docs_by_id, {}):
            raise ValueError(f"restored record {citation}: quoted_span not found in {r.get('source_doc_id')}")
        r["review_note"] = _cat(r.get("review_note"), "Restored as its own record: a later consolidation had "
                                "merged it into the § 37.9(a) record.")
        restored.append(r)
    return restored


def _current_as_candidates(rules: list[dict]) -> list[dict]:
    out = []
    for rule in rules:
        candidate = copy.deepcopy(rule)
        candidate["candidate_id"] = f"existing:{rule['team_rule_id']}"
        candidate["coverage"] = {**(rule.get("coverage_conditions") or {}), **(rule.get("coverage") or {})}
        out.append(candidate)
    return out


async def run_incremental(args, current: dict | None = None) -> dict:
    if not args.docs:
        raise ValueError("incremental mode requires --docs")
    llm_kwargs = {"concurrency": args.concurrency, "offline": args.offline or None}
    if getattr(args, "audit_path", None) is not None:
        llm_kwargs["audit_path"] = args.audit_path
    llm = LLM(**llm_kwargs)
    docs, links = load()
    docs_by_id = {d.doc_id: d for d in docs}
    wanted = set(args.docs)
    todo = [d for d in docs if d.doc_id in wanted]
    missing = wanted - {d.doc_id for d in todo}
    if missing:
        raise ValueError(f"unknown document ids: {sorted(missing)}")
    current = current or json.loads((OUT / "rules.json").read_text(encoding="utf-8"))
    old_rules = current["rules"]
    failures: list[dict] = []

    async def safe(label, coro, default):
        try:
            return await coro
        except Exception as exc:
            log.error("%s failed: %s", label, str(exc)[:200])
            failures.append({"step": label, "error": str(exc)[:300]})
            return default

    extracted = await asyncio.gather(*(safe(f"extract {d.doc_id}", extract_doc(llm, d),
                                             {"rules": [], "no_rule_findings": [], "doc_summary": ""})
                                       for d in todo))
    rejected: list = []
    repairs: list = []
    new_candidates: list[dict] = []
    verified = await asyncio.gather(*(verify_doc(llm, d, result["rules"], rejected, repairs)
                                      for d, result in zip(todo, extracted)))
    for doc, candidates in zip(todo, verified):
        for candidate in candidates:
            candidate["method"] = "document"
            allowed = INCREMENTAL_CATEGORY_SCOPE.get(doc.doc_id)
            if allowed is not None and candidate.get("category") not in allowed:
                rejected.append({"candidate_id": candidate["candidate_id"], "doc_id": doc.doc_id,
                                 "rule": candidate,
                                 "reason": "outside the approved incremental category scope"})
                continue
            new_candidates.append(candidate)
    if failures:
        raise SystemExit("incremental extraction failed; no canonical output was written")

    touched = sorted({c["jurisdiction"] for c in new_candidates})
    existing_candidates = _current_as_candidates(old_rules)
    dropped: list = []
    discarded: list = []
    qa_log: list = []
    merge_log: list = []
    fresh_raw: list[dict] = []

    for jurisdiction in touched:
        old_jur = [c for c in existing_candidates if c["jurisdiction"] == jurisdiction]
        new_jur = [c for c in new_candidates if c["jurisdiction"] == jurisdiction]
        candidates = old_jur + new_jur
        state_context = [r for r in old_rules if r["jurisdiction"] == jurisdiction[-2:]]
        consolidated = await consolidate(llm, jurisdiction, candidates, docs, links, state_context, dropped)
        flags = merge_findings(consolidated, {c["candidate_id"]: c for c in candidates})
        if flags:
            consolidated = await consolidate(
                llm, jurisdiction, candidates, docs, links, state_context, dropped, feedback=flags
            )
            merge_log.append({"jurisdiction": jurisdiction, "flags": flags})
        for index, rule in enumerate(consolidated):
            members = rule.get("from_candidates") or []
            if members and all(member.startswith("existing:") for member in members):
                continue
            rule["candidate_id"] = rule.get("candidate_id") or f"{jurisdiction}#incremental-{index}"
            jdocs = _docs_for(jurisdiction, [rule], docs)
            await audit_coverage(llm, rule, jdocs, docs_by_id, discarded)
            await audit_dates(llm, rule, jdocs, docs_by_id)
            pre_qa = copy.deepcopy(rule)
            await legal_qa(llm, rule, jdocs, qa_log)
            await verify_fields(llm, rule, docs_by_id, pre_qa)
            await resource(llm, rule, jdocs, docs_by_id)
            await plain_language(llm, rule)
            if not reverify_span(rule, docs_by_id, {c["candidate_id"]: c for c in candidates}):
                rejected.append({"candidate_id": rule["candidate_id"], "doc_id": rule.get("source_doc_id"),
                                 "rule": rule, "reason": "incremental consolidated quote not verified"})
                continue
            fresh_raw.append(rule)

    fresh_raw += await restore_absorbed_citations(llm, old_rules, docs, docs_by_id)
    fresh = finalize(fresh_raw, docs_by_id, old_rules, global_passes=False)
    replaced_ids = {r["team_rule_id"] for r in fresh}
    combined = [copy.deepcopy(r) for r in old_rules if r["team_rule_id"] not in replaced_ids] + fresh
    curation_log = curation.apply(combined, docs_by_id)
    ids.assign(combined, old_rules)
    ids.fill_overrides(combined)
    combined = [{k: r.get(k) for k in RECORD_FIELDS}
                for r in sorted(combined, key=lambda r: r["team_rule_id"])]
    findings = _dedupe_findings(current.get("no_rule_findings", []), combined)
    return {
        "rules": combined,
        "no_rule_findings": findings,
        "_rejected": rejected,
        "_repairs": repairs,
        "_dropped": dropped,
        "_discarded": discarded,
        "_qa": qa_log,
        "_merge": merge_log,
        "_curation": curation_log,
        "_conflicts": {"final": sum(bool(r.get("conflict_flag")) for r in combined)},
        "_cells": {},
    }


def curate_current() -> dict:
    docs, _ = load()
    docs_by_id = {d.doc_id: d for d in docs}
    current = json.loads((OUT / "rules.json").read_text(encoding="utf-8"))
    old_rules = current["rules"]
    rules = copy.deepcopy(old_rules)
    curation_log = curation.apply(rules, docs_by_id)
    ids.assign(rules, old_rules)
    ids.fill_overrides(rules)
    rules = [{k: r.get(k) for k in RECORD_FIELDS} for r in sorted(rules, key=lambda r: r["team_rule_id"])]
    findings = _dedupe_findings(current.get("no_rule_findings", []), rules)
    return {
        "rules": rules, "no_rule_findings": findings,
        "_rejected": [], "_repairs": [], "_dropped": [], "_discarded": [], "_qa": [], "_merge": [],
        "_curation": curation_log,
        "_conflicts": {"final": sum(bool(r.get("conflict_flag")) for r in rules)}, "_cells": {},
    }


async def run(args) -> dict:
    llm_kwargs = {"concurrency": args.concurrency, "offline": args.offline or None}
    if getattr(args, "audit_path", None) is not None:
        llm_kwargs["audit_path"] = args.audit_path
    llm = LLM(**llm_kwargs)
    docs, links = load()
    docs_by_id = {d.doc_id: d for d in docs}
    todo = [d for d in docs if not args.docs or d.doc_id in args.docs]

    failures: list = []

    async def safe(label, coro, default):
        try:
            return await coro
        except Exception as e:
            log.error("%s failed: %s", label, str(e)[:200])
            failures.append({"step": label, "error": str(e)[:300]})
            return default

    extractions = await asyncio.gather(*(safe(f"extract {d.doc_id}", extract_doc(llm, d),
                                              {"rules": [], "no_rule_findings": [], "doc_summary": ""}) for d in todo))
    rejected, repairs = [], []
    cands, findings = [], []
    verified = await asyncio.gather(*(verify_doc(llm, d, e["rules"], rejected, repairs)
                                      for d, e in zip(todo, extractions)))
    for e, v in zip(extractions, verified):
        for c in v:
            c["method"] = "document"
        cands += v
        findings += [f for f in e["no_rule_findings"]
                     if not f.get("quoted_span") or verify_against(docs_by_id, f["doc_id"], f["quoted_span"])]

    cell_results = [] if args.docs else [c for c in await C.collect_all_cells(llm, docs, safe) if c]
    cell_status = {}
    for c in cell_results:
        cands += c["rules"]
        rejected += [{"candidate_id": f"cell:{x['cell']}", **x} for x in c["rejected"]]
        cell_status[(c["jurisdiction"], c["category"])] = c["status"]
        if c["finding"]:
            findings.append(c["finding"])
    cand_by_id = {c["candidate_id"]: c for c in cands}

    jurs = sorted({c["jurisdiction"] for c in cands} | {normalize_jurisdiction(j) for d in docs
                                                         for j in d.jurisdictions.split(";") if j.strip()})
    dropped: list = []
    merge_log: list = []
    states = [j for j in jurs if len(j) == 2]
    cities = [j for j in jurs if len(j) != 2]

    async def consolidate_checked(j, context):
        jc = [c for c in cands if c["jurisdiction"] == j]
        rs = await consolidate(llm, j, jc, docs, links, context, dropped)
        flags = merge_findings(rs, {c["candidate_id"]: c for c in jc})
        if flags:
            rs2 = await consolidate(llm, j, jc, docs, links, context, [], feedback=flags)
            merge_log.append({"jurisdiction": j, "flags": flags, "before": len(rs), "after": len(rs2)})
            rs = rs2
        return rs

    res = await asyncio.gather(*(consolidate_checked(j, [c for c in cands if c["jurisdiction"].endswith(", " + j)])
                                 for j in states))
    state_rules = dict(zip(states, res))
    res = await asyncio.gather(*(consolidate_checked(j, state_rules.get(j[-2:], [])) for j in cities))
    by_jur = {**state_rules, **dict(zip(cities, res))}

    index = Index(docs)
    probes = await asyncio.gather(*(probe(llm, j, by_jur[j], docs, docs_by_id, index) for j in jurs))
    findings += [p for ps in probes for p in ps]

    discarded, qa_log = [], []
    all_rules = []
    for j in jurs:
        for i, r in enumerate(by_jur[j]):
            r["candidate_id"] = r.get("candidate_id") or f"{j}#{i}"
            all_rules.append((j, r))
    reconcile_methods([r for _, r in all_rules], cand_by_id)
    conflicts_before = sum(bool(r.get("conflict_flag")) for _, r in all_rules)

    async def audit(j, r):
        jdocs = _docs_for(j, [r], docs)
        await audit_coverage(llm, r, jdocs, docs_by_id, discarded)
        await audit_dates(llm, r, jdocs, docs_by_id)
        pre_qa = copy.deepcopy(r)
        await legal_qa(llm, r, jdocs, qa_log)
        await verify_fields(llm, r, docs_by_id, pre_qa)
        await resource(llm, r, jdocs, docs_by_id)
        await plain_language(llm, r)
    await asyncio.gather(*(safe(f"audit {r['candidate_id']}", audit(j, r), None) for j, r in all_rules))
    if failures:
        log.error("%d call(s) failed: %s", len(failures), failures[:5])
        if not getattr(args, "allow_failures", False):
            raise SystemExit("some calls failed; rerun to retry them from the cache (or pass --allow-failures)")

    kept = []
    for j, r in all_rules:
        if j not in C.TARGET_AREAS:
            dropped.append({"jurisdiction": j, "candidate_id": r["candidate_id"], "reason": "out of scope"})
            continue
        if not reverify_span(r, docs_by_id, cand_by_id):
            rejected.append({"candidate_id": r["candidate_id"], "doc_id": r.get("source_doc_id"), "rule": r,
                             "reason": "consolidated quoted_span not found in any member document"})
            continue
        kept.append(r)
    kept = adopted_over_proposed(kept, dropped)
    kept += await restore_absorbed_citations(llm, kept, docs, docs_by_id)
    old = json.loads((OUT / "rules.json").read_text(encoding="utf-8"))["rules"]
    try:
        old = json.loads((ROOT / "out" / "rules_baseline.json").read_text(encoding="utf-8"))["rules"]
    except FileNotFoundError:
        pass
    curation_log: list = []
    final = finalize(kept, docs_by_id, old, curation_log=curation_log)
    findings += state_bar_findings(final)
    findings = _dedupe_findings(findings, final)
    return {"rules": final, "no_rule_findings": findings, "_rejected": rejected, "_repairs": repairs,
            "_dropped": dropped, "_discarded": discarded, "_qa": qa_log, "_merge": merge_log,
            "_curation": curation_log,
            "_conflicts": {"before_qa": conflicts_before, "final": sum(bool(r.get("conflict_flag")) for r in final)},
            "_cells": {f"{j}|{c}": s for (j, c), s in sorted(cell_status.items())}}


def reverify_span(r: dict, docs_by_id, cand_by_id) -> bool:
    d = docs_by_id.get(r.get("source_doc_id"))
    if d:
        got, _ = exact_or_normalized(d.raw, r.get("quoted_span"))
        if got:
            r["quoted_span"] = got
            return True
    for cid in r.get("from_candidates", []):
        c = cand_by_id.get(cid)
        if c and c.get("source_doc_id") in docs_by_id:
            got, _ = exact_or_normalized(docs_by_id[c["source_doc_id"]].raw, c.get("quoted_span"))
            if got:
                r["source_doc_id"], r["quoted_span"] = c["source_doc_id"], got
                return True
    if d and r.get("quoted_span"):
        got, _ = snap(d.raw, r["quoted_span"])
        if got:
            r["quoted_span"] = got
            return True
    return False


def adopted_over_proposed(rules: list[dict], dropped: list) -> list[dict]:
    from ..normalize import law_key

    enacted = {(r["jurisdiction"], r["category"], law_key(r["citation"])) for r in rules
               if r["status"] in ("in_force", "not_yet_effective")}
    seen_pending, out = set(), []
    for r in rules:
        k = (r["jurisdiction"], r["category"], law_key(r["citation"]))
        if r["status"] == "pending":
            if k in enacted or k in seen_pending:
                dropped.append({"candidate_id": r["candidate_id"], "reason": "proposed version of an adopted or "
                                "already listed law"})
                continue
            seen_pending.add(k)
        out.append(r)
    return out


def state_bar_findings(rules: list[dict]) -> list[dict]:
    out = []
    for r in rules:
        if len(r["jurisdiction"]) != 2 or r["category"] != "rent_increase_limits":
            continue
        text = f"{r.get('title', '')} {r.get('requirement', '')}".lower()
        if "rent control" in text and any(w in text for w in ("prohibit", "bar", "ban", "may not", "no city")):
            for city in C.TARGET_AREAS:
                if city.endswith(", " + r["jurisdiction"]):
                    out.append({"jurisdiction": city, "category": "rent_increase_limits", "kind": "no_rule",
                                "doc_id": r["source_doc_id"], "quoted_span": r["quoted_span"],
                                "basis_citation": r["citation"],
                                "reason": f"local rent control barred by {r['citation']}"})
    return out


def _dedupe_findings(findings: list[dict], rules: list[dict]) -> list[dict]:
    covered = {(r["jurisdiction"], r["category"]) for r in rules if r["status"] == "in_force"}
    seen, out = set(), []
    for f in sorted(findings, key=lambda f: (f["jurisdiction"], f["category"], f.get("kind") != "no_rule",
                                             f.get("doc_id") or "", f.get("quoted_span") or "")):
        if f.get("kind") != "no_rule" or not all(
                str(f.get(k) or "").strip() for k in ("doc_id", "quoted_span", "basis_citation")):
            continue
        key = (f["jurisdiction"], f["category"])
        if key in seen or key in covered:
            continue
        seen.add(key)
        out.append({
            "jurisdiction": f["jurisdiction"],
            "category": f["category"],
            "citation": f["basis_citation"],
            "quoted_span": f["quoted_span"],
            "reason": f.get("reason") or "The cited source states that no rule is in force in this cell.",
            "source_doc_id": f["doc_id"],
        })
    return out


def write(result: dict, out: Path = OUT) -> None:
    (out / "rules.json").write_text(ids.dump({"rules": result["rules"], "no_rule_findings": result["no_rule_findings"]}),
                                    encoding="utf-8")
    for k, key in (("_rejected", "candidate_id"), ("_repairs", "candidate_id"), ("_discarded", "rule")):
        result[k].sort(key=lambda x: (x.get(key) or "", json.dumps(x, sort_keys=True)))
    result["_dropped"].sort(key=lambda x: json.dumps(x, sort_keys=True))
    result["_qa"].sort(key=lambda x: (x["rule"], x["field"]))
    (out / "rejected.json").write_text(ids.dump(result["_rejected"]), encoding="utf-8")
    (out / "rules_raw.json").write_text(ids.dump({"repairs": result["_repairs"], "dropped": result["_dropped"],
                                                  "coverage_discarded": result["_discarded"],
                                                  "merge_check": result.get("_merge", []),
                                                  "evidence_corrections": result.get("_curation", []),
                                                  "conflict_flags": result.get("_conflicts"),
                                                  "cells": result.get("_cells")}), encoding="utf-8")
    with (out / "qa_changes.jsonl").open("w", encoding="utf-8") as f:
        for row in result["_qa"]:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="extraction.v3.pipeline")
    p.add_argument("--offline", action="store_true", help="cache only; fail on a miss")
    p.add_argument("--docs", nargs="+")
    p.add_argument("--concurrency", type=int, default=12)
    p.add_argument("--dry-run", action="store_true", help="do not write out/")
    p.add_argument("--merge-current", action="store_true",
                   help="with --docs, update only touched jurisdictions and merge into current out/rules.json")
    p.add_argument("--curate-current", action="store_true",
                   help="reapply deterministic evidence corrections to the canonical output without model calls")
    p.add_argument("--allow-failures", action="store_true")
    p.add_argument("--out-dir", type=Path, default=OUT)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.merge_current and not args.docs:
        p.error("--merge-current requires --docs")
    if args.curate_current and (args.docs or args.merge_current):
        p.error("--curate-current cannot be combined with --docs or --merge-current")
    result = curate_current() if args.curate_current else asyncio.run(
        run_incremental(args) if args.merge_current else run(args)
    )
    if not args.dry_run:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        write(result, args.out_dir)
    log.info("conflict flags %s", result.get("_conflicts"))
    log.info("%d rules, %d no-rule findings, %d rejected spans, %d repaired, %d QA changes",
             len(result["rules"]), len(result["no_rule_findings"]), len(result["_rejected"]),
             len(result["_repairs"]), len(result["_qa"]))


if __name__ == "__main__":
    main()
