from __future__ import annotations

CATEGORIES = ["rent_increase_limits", "just_cause_eviction", "security_deposits",
              "application_screening_fees", "screening_restrictions", "algorithmic_rent_setting"]
STATUSES = ["in_force", "not_yet_effective", "pending", "failed"]


def _obj(props: dict, nullable: bool = False) -> dict:
    t = ["object", "null"] if nullable else "object"
    return {"type": t, "additionalProperties": False, "properties": props, "required": list(props)}


def _s(nullable=True):
    return {"type": ["string", "null"]} if nullable else {"type": "string"}


def _i():
    return {"type": ["integer", "null"]}


def _b():
    return {"type": ["boolean", "null"]}


def _arr(items):
    return {"type": "array", "items": items}


DATE_FORMULA = _obj({
    "kind": {"type": "string", "enum": ["first_day_of_nth_month_following", "nth_month_after", "days_after",
                                         "on_date"]},
    "n": _i(), "anchor": {"type": "string", "enum": ["enactment", "approval", "adoption", "publication"]},
    "anchor_date": _s(), "verbatim": _s(False),
}, nullable=True)

COVERAGE_SCHEMA = _obj({
    "summary": _s(),
    "min_units": _i(), "max_units": _i(),
    "construction_date_basis": _s(), "built_on_or_before": _s(), "built_after": _s(),
    "construction_cutoff": _obj({
        "basis": {"type": "string", "enum": ["year_built", "certificate_of_occupancy", "first_occupancy"]},
        "covered_if": {"type": "string", "enum": ["on_or_before", "before", "after", "on_or_after"]},
        "date": _s(False)}, nullable=True),
    "min_building_age_years": _i(),
    "new_construction_exemption": _obj({"years": _i(), "basis": _s(), "requires_owner_filing": _b()},
                                       nullable=True),
    "owner_occupied_exemption_max_units": _i(),
    "landlord_size_condition": _s(),
    "owner_conditions": _s(), "other_conditions": _s(),
    "unverifiable_exemptions": _arr(_s(False)),
    "requires_unknown_facts": _b(),
    "yields_to_local_rule": _b(), "supersedes_state_rule": _b(), "may_preempt_local_rules": _b(),
})

RULE = _obj({
    "candidate_id": _s(False),
    "jurisdiction": _s(False), "category": {"type": "string", "enum": CATEGORIES},
    "status": {"type": "string", "enum": STATUSES},
    "title": _s(False), "requirement": _s(False), "key_value": _s(),
    "coverage": COVERAGE_SCHEMA, "exemptions": _s(),
    "event_only": {"type": "boolean"}, "applies_only_in": _s(),
    "effective_date": _s(), "enacted_date": _s(), "sunset_date": _s(), "effective_date_note": _s(),
    "effective_date_formula": DATE_FORMULA,
    "citation": _s(False), "citation_aliases": _arr(_s(False)),
    "quoted_span": _s(False), "confidence": {"type": "number"},
    "conflict_flag": {"type": "boolean"}, "conflict_note": _s(), "review_note": _s(), "source_notes": _s(),
})

NO_RULE = _obj({
    "jurisdiction": _s(False), "category": {"type": "string", "enum": CATEGORIES},
    "finding": _s(False), "kind": {"type": "string", "enum": ["no_rule", "motion", "study", "other"]},
    "quoted_span": _s(), "basis_citation": _s(),
})

EXTRACTION = _obj({"rules": _arr(RULE), "no_rule_findings": _arr(NO_RULE), "doc_summary": _s(False)})

RECOPY = _obj({"spans": _arr(_obj({"candidate_id": _s(False), "quoted_span": _s()}))})

CONSOLIDATED_RULE = _obj({
    **RULE["properties"],
    "source_doc_id": _s(False),
    "from_candidates": _arr(_s(False)),
    "also_supported_by": _arr(_obj({"doc_id": _s(False), "quoted_span": _s(False)})),
})

CONSOLIDATION = _obj({
    "rules": _arr(CONSOLIDATED_RULE),
    "dropped_candidates": _arr(_obj({"candidate_id": _s(False), "reason": _s(False)})),
    "known_gaps": _arr(_obj({"category": _s(False), "law": _s(False), "reason": _s(False)})),
})

PROBE = _obj({"verdicts": _arr(_obj({
    "category": {"type": "string", "enum": CATEGORIES},
    "verdict": {"type": "string", "enum": ["no_rule", "undetermined"]},
    "doc_id": _s(), "quoted_span": _s(), "basis_citation": _s(), "reason": _s(False)}))})

COVERAGE_AUDIT = _obj({
    "coverage": COVERAGE_SCHEMA,
    "evidence": _arr(_obj({"field": _s(False), "doc_id": _s(False), "quoted_span": _s(False)})),
    "notes": _s(),
})

DATE_AUDIT = _obj({
    "requirement_is_new": _b(), "in_force_since": _s(),
    "in_force_since_evidence": _obj({"doc_id": _s(False), "quoted_span": _s(False)}, nullable=True),
    "current_version_effective": _s(), "prior_version_note": _s(),
    "effective_date_formula": DATE_FORMULA,
})

QA_FIELDS = ["category", "status", "effective_date", "in_force_since", "current_version_effective",
             "coverage.construction_cutoff", "applies_only_in", "event_only", "conflict_flag",
             "conflict_note", "citation"]

QA = _obj({"changes": _arr(_obj({
    "field": {"type": "string", "enum": QA_FIELDS},
    "after_json": _s(False), "reason": _s(False)}))})

RESOURCE = _obj({"replacement": _obj({"doc_id": _s(False), "quoted_span": _s(False)}, nullable=True),
                 "reason": _s(False)})

CELL = _obj({
    "cell_status": {"type": "string", "enum": ["rules_found", "no_rule_stated", "silent"]},
    "no_rule_quote": _s(), "no_rule_passage_id": _s(), "basis_citation": _s(),
    "rules": _arr(_obj({**{k: v for k, v in RULE["properties"].items() if k != "candidate_id"},
                        "passage_id": _s(False)})),
})

FIELD_VERDICT = {"type": "string", "enum": ["supported", "partly_supported", "not_supported", "not_applicable"]}
VERIFY_FIELDS = ["requirement", "key_value", "effective_date", "status", "coverage", "citation"]
FIELD_CHECK = _obj({"fields": _arr(_obj({
    "field": {"type": "string", "enum": VERIFY_FIELDS}, "verdict": FIELD_VERDICT,
    "quoted_span": _s(), "note": _s()}))})

PLAIN = _obj({"en": _s(False), "es": _s(False)})
