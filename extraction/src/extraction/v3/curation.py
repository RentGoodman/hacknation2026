from __future__ import annotations

import copy
import re
from pathlib import Path

from .client import ROOT
from .verify import exact_or_normalized


def _proof(docs_by_id, doc_id: str, span: str) -> str:
    if doc_id == "BRIEF":
        text = (ROOT / "starter pack" / "README.md").read_text(encoding="utf-8")
        if span not in text:
            raise AssertionError(f"brief evidence not found: {span}")
        return span
    doc = docs_by_id.get(doc_id)
    if not doc:
        raise AssertionError(f"missing evidence document {doc_id}")
    got, _ = exact_or_normalized(doc.raw, span)
    if not got:
        raise AssertionError(f"evidence not found in {doc_id}: {span}")
    return got


def _match(r: dict, jurisdiction: str, category: str, citation_part: str) -> bool:
    return (r.get("jurisdiction") == jurisdiction and r.get("category") == category
            and citation_part.lower() in (r.get("citation") or "").lower())


DATE_FIXES = [
    ("CA", "algorithmic_rent_setting", "16729", "2026-01-01", "DX09",
     "These laws, described below, took effect on January 1, 2026."),
    ("Los Angeles, CA", "just_cause_eviction", "151.09", "2023-01-27", "D040",
     "All landlords of residential properties must provide a Notice of Renters’ Protections to tenants who begin or renew their tenancy on or after January 27, 2023."),
    ("NJ", "just_cause_eviction", "2A:18-61.1", "1974", "D065",
     "Notwithstanding any provision of the Anti-Eviction Act, P.L.1974, c.49"),
    ("Jersey City, NJ", "algorithmic_rent_setting", "218-12", "2025-06", "DX06",
     "Jersey City Code § 218-12 (effective June 2025)"),
    ("Berkeley, CA", "screening_restrictions", "13.106", "2020", "D003",
     "On April 14, 2020, Berkeley City Council passed the Fair Chance Access to Housing Ordinance (BMC 13.106)."),
    ("CA", "screening_restrictions", "12264", "2020-01-01", "DX07",
     "In 2019, California’s Civil Rights Council (formerly the Fair Employment and Housing Council) enacted regulations that took effect Jan. 1, 2020"),
    ("Hoboken, NJ", "algorithmic_rent_setting", "158-2", "2025-07", "DX06",
     "Hoboken City Code, ch. 158-2 (effective July 2025)"),
    ("MA", "application_screening_fees", "186, § 15B", "2025-08-01", "D052",
     "as amended by 2025, 9, Secs. 54 and 55 effective August 1, 2025"),
    ("San Francisco, CA", "just_cause_eviction", "37.9C", "2026-03-01", "D083",
     "3/01/26 - 2/28/27\n$8,245.00\n$24,733.00\n$5,497.00"),
]


KEY_VALUE_FIXES = [
    ("Berkeley, CA", "algorithmic_rent_setting", "13.63.030",
     "Ban on selling or using coordinated pricing algorithms to set rents or occupancy levels",
     "D001", "It shall be unlawful for a landlord to use a coordinated pricing algorithm described"),
    ("Los Angeles, CA", "just_cause_eviction", "151.09",
     "Eviction only for an RSO just cause; no-fault evictions require relocation assistance",
     "D041", "No-fault evictions require the payment of"),
    ("NJ", "just_cause_eviction", "2A:18-61.1",
     "Eviction or nonrenewal only for a statutory good cause",
     "D067", "No residential landlord may evict or fail to renew a lease, whether it is a written or an oral lease without good cause."),
    ("Jersey City, NJ", "algorithmic_rent_setting", "218-12",
     "Ban on landlord use of algorithmic rent coordination services; fines up to $2,000 per day",
     "DX02", "It is unlawful for any real estate lessor, agent, or subcontractor thereof, to subscribe to, contract with, or otherwise"),
    ("Berkeley, CA", "screening_restrictions", "13.106",
     "No criminal-history inquiries or use in rental housing decisions",
     "D003", "prohibits rental housing providers in Berkeley from asking about and using criminal history"),
    ("Hoboken, NJ", "algorithmic_rent_setting", "158-2",
     "Ban on software, algorithms or data-sharing platforms that coordinate rents, lease terms or occupancy",
     "DX01", "are prohibited from price fixing using algorithmic pricing"),
    ("NJ", "just_cause_eviction", "2A:42-10.10",
     "No eviction, substantial lease change or refusal to renew in retaliation for protected tenant activity",
     "D067", "A landlord cannot take reprisal action against a tenant by eviction"),
    ("Los Angeles, CA", "just_cause_eviction", "47.06",
     "Relocation assistance required when a rental property is demolished or converted",
     "D043", "All tenant not- at-fault evictions require payment of relocation assistance"),
    ("Los Angeles, CA", "just_cause_eviction", "188481",
     "Protected-unit demolition requires relocation, notice and occupant protections; the highest applicable state or city relocation amount must be paid",
     "D043", "The owner must pay the highest of the applicable relocation amounts to comply with State"),
    ("San Diego, CA", "algorithmic_rent_setting", "98.1103",
     "Ban on providing or using algorithmic devices that set rents or occupancy from nonpublic competitor data",
     "D076", "It is unlawful for a landlord to use an algorithmic device to set rental rates"),
    ("Santa Ana, CA", "algorithmic_rent_setting", "NS-3090",
     "Ban on selling, licensing, providing or using algorithmic rent-setting software for residential rentals",
     "DX06", "Ordinance NS-3090 prohibits specified anticompetitive automated rent price-fixing"),
    ("San Francisco, CA", "just_cause_eviction", "37.9C",
     "Landlord must pay relocation to tenants evicted for owner/relative move-in, demolition or permanent removal, "
     "temporary capital improvement work or substantial rehabilitation: $8,245.00 per tenant, max $24,733.00 per "
     "unit, plus $5,497.00 per elderly (60+) or disabled tenant or household with minor children "
     "(notices served 3/1/2026-2/28/2027)",
     "D083", "Relocation Payments for Evictions based on Owner/Relative Move-in OR Demolition/Permanent Removal of Unit from Housing Use OR Temporary Capital Improvement Work* OR Substantial Rehabilitation"),
    ("Santa Ana, CA", "algorithmic_rent_setting", "first reading",
     "Proposed ban on selling, licensing, providing or using algorithmic rent-setting software for residential rentals",
     "DX19", "prohibits the sale, licensing, provision and use of certain algorithmic rent-setting software"),
]


def _append_evidence(rule: dict, field: str, doc_id: str, span: str) -> None:
    verification = rule.setdefault("verification", {"verdicts": {}, "evidence": [], "changes": []})
    verification.setdefault("verdicts", {})[field] = "supported"
    evidence = verification.setdefault("evidence", [])
    item = {"field": field, "doc_id": doc_id, "quoted_span": span}
    if doc_id != "BRIEF" and item not in evidence:
        evidence.append(item)


def _add_nj_unconscionable_rule(rules: list[dict], docs_by_id, log: list[dict]) -> None:
    base = next((r for r in rules if _match(r, "NJ", "just_cause_eviction", "2A:18-61.1")), None)
    if not base:
        return
    existing = next((r for r in rules if _match(r, "NJ", "rent_increase_limits", "2A:18-61.1(f)")), None)
    if existing:
        for field in ("level", "source_url", "coverage_conditions"):
            if existing.get(field) is None and base.get(field) is not None:
                existing[field] = copy.deepcopy(base[field])
        return
    span = _proof(
        docs_by_id, "D067",
        "The rent increase must not be unconscionable and must comply with all other laws or municipal ordinances, including rent control."
    )
    rule = copy.deepcopy(base)
    for field in ("team_rule_id", "canonical_id"):
        rule.pop(field, None)
    rule.update({
        "candidate_id": "derived:D067:2A18-61.1f",
        "category": "rent_increase_limits",
        "title": "New Jersey protection against unconscionable rent increases",
        "requirement": ("A landlord may use nonpayment of an increased rent as an eviction ground only when "
                        "the increase is not unconscionable and complies with all applicable laws and municipal rent control."),
        "key_value": "Rent increase must not be unconscionable and must comply with municipal rent control",
        "citation": "N.J.S.A. 2A:18-61.1(f)",
        "citation_aliases": ["New Jersey Anti-Eviction Act"],
        "source_doc_id": "D067",
        "quoted_span": span,
        "also_supported_by": [],
        "effective_date": "1974",
        "effective_date_note": "The source identifies subsection (f) of the Anti-Eviction Act, P.L.1974, c.49.",
        "plain_language": {
            "en": "A rent increase used to support an eviction must not be unconscionable and must follow local rent-control law.",
            "es": "Un aumento de alquiler usado para justificar un desalojo no puede ser abusivo y debe cumplir el control local de alquileres.",
        },
        "found_by": ["derived_from_captured_text"],
        "conflict_flag": False,
        "conflict_note": None,
        "review_note": "Separate category record derived from the expressly identified subsection in D067.",
    })
    rule["verification"] = {
        "verdicts": {f: "supported" for f in ("requirement", "key_value", "effective_date", "status", "coverage", "citation")},
        "evidence": [{"field": f, "doc_id": "D067", "quoted_span": span}
                     for f in ("requirement", "key_value", "status", "coverage", "citation")],
        "changes": [],
    }
    rules.append(rule)
    log.append({"kind": "derived_rule", "citation": rule["citation"], "evidence_doc_id": "D067"})


def _split_ca_source_income_rule(rules: list[dict], docs_by_id, log: list[dict]) -> None:
    base = next((r for r in rules if r.get("jurisdiction") == "CA"
                 and r.get("category") == "screening_restrictions"
                 and (r.get("citation") or "").strip().endswith("§ 12955")), None)
    if not base:
        return
    general_span = _proof(
        docs_by_id, "D027",
        "For the owner of any housing accommodation to discriminate against or harass any person because of the race, color, religion, sex, gender, gender identity, gender expression, sexual orientation, marital status, national origin, ancestry, familial status, source of income, disability, veteran or military status, or genetic information of that person."
    )
    base.update({
        "title": "FEHA statewide protection against source-of-income discrimination",
        "requirement": ("Housing owners may not discriminate against or harass a person because of source of "
                        "income. Protected income includes public assistance and housing subsidies such as "
                        "Section 8 and HUD-VASH vouchers, and discriminatory rental advertising is prohibited."),
        "key_value": "No housing discrimination based on lawful source of income, including housing vouchers",
        "quoted_span": general_span,
    })
    base.setdefault("coverage_conditions", {})["summary"] = (
        "Applies statewide to owners of housing accommodations and housing providers."
    )
    base["coverage_conditions"]["other_conditions"] = None
    base.setdefault("coverage", {})["requires_unknown_facts"] = False
    base["verification"] = {
        "verdicts": {f: "supported" for f in ("requirement", "key_value", "effective_date", "status", "coverage", "citation")},
        "evidence": [{"field": f, "doc_id": "D027", "quoted_span": general_span}
                     for f in ("requirement", "key_value", "status", "coverage", "citation")],
        "changes": [],
    }

    rules[:] = [r for r in rules if not (
        r is not base and r.get("jurisdiction") == "CA"
        and r.get("category") == "screening_restrictions"
        and "12955(o)" in (r.get("citation") or "")
    )]


def apply(rules: list[dict], docs_by_id) -> list[dict]:
    log: list[dict] = []
    _add_nj_unconscionable_rule(rules, docs_by_id, log)
    _split_ca_source_income_rule(rules, docs_by_id, log)

    for rule in rules:
        citation = rule.get("citation") or ""
        if rule.get("jurisdiction") == "CA" and ("1946.2" in citation or "1947.9" in citation):
            coverage = rule.setdefault("coverage", {})
            if coverage.get("may_preempt_local_rules"):
                coverage["may_preempt_local_rules"] = False
                log.append({"kind": "false_preemption_coverage_removed", "citation": citation})

    nj_span = _proof(
        docs_by_id, "D067",
        "newly constructed multiple dwellings shall be exempt from any local rent control ordinances for a period of 30 years following completion of construction of the building."
    )
    for rule in rules:
        if not (rule.get("jurisdiction", "").endswith(", NJ")
                and rule.get("category") == "rent_increase_limits"):
            continue
        coverage = rule.setdefault("coverage", {})
        if coverage.get("new_construction_exemption"):
            continue
        coverage["new_construction_exemption"] = {
            "years": 30,
            "basis": "completion of construction",
            "requires_owner_filing": False,
        }
        evidence = rule.setdefault("coverage_evidence", [])
        item = {"field": "new_construction_exemption", "doc_id": "D067", "quoted_span": nj_span}
        if item not in evidence:
            evidence.append(item)
        log.append({"kind": "nj_new_construction_exemption", "citation": rule.get("citation"),
                    "evidence_doc_id": "D067"})

    berkeley = next((r for r in rules if _match(r, "Berkeley, CA", "algorithmic_rent_setting", "13.63")), None)
    if berkeley:
        phrase = _proof(
            docs_by_id, "BRIEF",
            "Berkeley's algorithmic ban** (ch. 13.63) has two published effective dates: March 1, 2026 in the ordinance text, January 2026 per an August 2026 law-firm alert."
        )
        before = berkeley.get("effective_date")
        berkeley["effective_date"] = "2026-03-01"
        berkeley["effective_date_note"] = (
            "The organizer brief reports March 1, 2026 from the ordinance text and January 2026 from a secondary alert. "
            "The captured D001 copy omits the operative-date clause, so the published conflict remains flagged."
        )
        berkeley["conflict_flag"] = True
        berkeley["conflict_note"] = (
            "Organizer open question: March 1, 2026 is reported from the ordinance text, while DX06 reports "
            "January 2026. The captured D001 copy omits the operative-date clause, so the disagreement remains "
            "visible for human review."
        )
        _append_evidence(berkeley, "effective_date", "BRIEF", phrase)
        log.append({"kind": "date", "citation": berkeley.get("citation"), "before": before,
                    "after": "2026-03-01", "evidence_doc_id": "BRIEF"})

    for jurisdiction, category, citation_part, value, doc_id, requested_span in DATE_FIXES:
        rule = next((r for r in rules if _match(r, jurisdiction, category, citation_part)), None)
        if not rule:
            continue
        span = _proof(docs_by_id, doc_id, requested_span)
        before = rule.get("effective_date")
        rule["effective_date"] = value
        _append_evidence(rule, "effective_date", doc_id, span)
        note = rule.get("effective_date_note") or ""
        normalized_span = re.sub(r"\s+", " ", span).strip()
        source_sentence = f"Evidence: {doc_id}: {normalized_span}"
        if source_sentence not in note:
            rule["effective_date_note"] = (note + " " + source_sentence).strip()
        log.append({"kind": "date", "citation": rule.get("citation"), "before": before,
                    "after": value, "evidence_doc_id": doc_id})

    for jurisdiction, category, citation_part, value, doc_id, requested_span in KEY_VALUE_FIXES:
        rule = next((r for r in rules if _match(r, jurisdiction, category, citation_part)), None)
        if not rule:
            continue
        span = _proof(docs_by_id, doc_id, requested_span)
        before = rule.get("key_value")
        rule["key_value"] = value
        _append_evidence(rule, "key_value", doc_id, span)
        log.append({"kind": "key_value", "citation": rule.get("citation"), "before": before,
                    "after": value, "evidence_doc_id": doc_id})

    for rule in rules:
        note = rule.get("conflict_note") or ""
        if not (rule.get("category") == "just_cause_eviction" and len(rule.get("jurisdiction") or "") > 2
                and ("1946.2 may preempt" in note or "1947.9 may preempt" in note
                     or note.startswith("A. Mun. Code"))):
            continue
        rule["conflict_note"] = None
        rule["conflict_flag"] = False
        log.append({"kind": "false_preemption_removed", "citation": rule.get("citation")})

    return log
