import asyncio as async_tasks
from collections import Counter as PassageCounts

from ..corpus import normalize_jurisdiction as canonicalize_area
from . import prompts as prompt_templates, schemas as response_schemas
from .bm25 import Index as PassageIndex
from .client import EXTRACT_MODEL as CELL_MODEL
from .verify import exact_or_normalized as locate_source_quote

TARGET_AREAS = [
    "CA",
    "NJ",
    "MA",
    "Berkeley, CA",
    "Los Angeles, CA",
    "San Diego, CA",
    "San Francisco, CA",
    "Santa Ana, CA",
    "Hoboken, NJ",
    "Jersey City, NJ",
    "Newark, NJ",
    "Boston, MA",
    "Cambridge, MA",
]

CATEGORY_SEARCH_TERMS = {
    "rent_increase_limits": (
        "rent rents increase increases limit limits cap caps maximum annual allowable "
        "adjustment adjustments control stabilization cpi consumer price index percent "
        "percentage inflation formula freeze moratorium preemption preempt"
    ),
    "just_cause_eviction": (
        "just cause eviction evictions terminate termination tenancy tenancies notice "
        "notices quit relocation assistance payment payments fault nonpayment breach "
        "owner occupancy withdrawal demolition conversion retaliation reprisal"
    ),
    "security_deposits": (
        "security deposit deposits maximum cap month months rent return refund refunds "
        "deadline deduction deductions itemized statement receipt receipts interest "
        "escrow account damage damages cleaning ordinary wear tear photographs"
    ),
    "application_screening_fees": (
        "application applications screening fee fees cap maximum charge charges cost "
        "costs actual pocket credit report reports reusable receipt receipts itemized "
        "refund refunds refundable nonrefundable unused upfront advance first last "
        "month key lock broker brokerage commission"
    ),
    "screening_restrictions": (
        "screening applicant applicants criminal history background arrest arrests "
        "conviction convictions record records credit score eviction income source "
        "voucher vouchers subsidy subsidies assistance discrimination fair chance "
        "conditional offer inquiry inquiries individualized assessment adverse denial"
    ),
    "algorithmic_rent_setting": (
        "algorithm algorithms algorithmic software device devices pricing price fixing "
        "rent rents rental setting coordinated coordinate coordination collusion "
        "anticompetitive antitrust competitor competitors nonpublic data sharing "
        "revenue management recommendation recommendations realpage"
    ),
}

_STATE_LABELS = {"CA": "California", "NJ": "New Jersey", "MA": "Massachusetts"}
LOCAL_SOURCE_WEIGHT, STARTER_SOURCE_WEIGHT = 1.8, 1.4
PASSAGE_BUDGET, RESERVED_STARTER_PASSAGES, DOCUMENT_PASSAGE_LIMIT = 10, 6, 3


def _source_areas(source):
    return {
        canonicalize_area(area_label)
        for area_label in source.jurisdictions.split(";")
        if area_label.strip()
    }


def _is_official_starter(source):
    return source.doc_id.startswith("D") and source.doc_id[1:].isdigit() and source.official


def retrieve_cell_context(search_index, sources_by_id, target_area, rule_category):
    target_area = canonicalize_area(target_area)
    topic_matches = search_index.scored(CATEGORY_SEARCH_TERMS[rule_category])
    place_terms = _STATE_LABELS.get(target_area, target_area.split(",")[0])
    place_scores = {
        passage_index: relevance for relevance, passage_index in search_index.scored(place_terms)
    }
    official_source_ids = {
        source_id for source_id, source in sources_by_id.items() if _is_official_starter(source)
    }
    source_weights = {
        source_id: (LOCAL_SOURCE_WEIGHT if target_area in _source_areas(source) else 1.0)
        * (STARTER_SOURCE_WEIGHT if source_id in official_source_ids else 1.0)
        for source_id, source in sources_by_id.items()
    }

    ranked_matches = [
        (
            (relevance + place_scores.get(passage_index, 0.0))
            * source_weights[search_index.passages[passage_index][0]],
            passage_index,
        )
        for relevance, passage_index in topic_matches
    ]
    ranked_matches.sort(key=lambda match: (-match[0], match[1]))

    selected_indexes = []
    selected_index_set = set()
    source_counts = PassageCounts()
    for reserve_starter, selection_limit in ((True, RESERVED_STARTER_PASSAGES), (False, PASSAGE_BUDGET)):
        for _relevance, passage_index in ranked_matches:
            if len(selected_indexes) >= selection_limit:
                break
            source_id = search_index.passages[passage_index][0]
            if passage_index in selected_index_set or source_counts[source_id] >= DOCUMENT_PASSAGE_LIMIT:
                continue
            if reserve_starter and source_id not in official_source_ids:
                continue
            selected_indexes.append(passage_index)
            selected_index_set.add(passage_index)
            source_counts[source_id] += 1

    return [
        (f"p{ordinal}", *search_index.passages[passage_index])
        for ordinal, passage_index in enumerate(selected_indexes, 1)
    ]


def _resolve_citation(sources_by_id, citations_by_id, citation_id, quotation):
    cited_context = citations_by_id.get(citation_id or "")
    if cited_context is None:
        return None
    source_id, excerpt = cited_context
    if not locate_source_quote(excerpt, quotation)[0]:
        return None
    original_quote, _match_kind = locate_source_quote(sources_by_id[source_id].raw, quotation)
    return (source_id, original_quote) if original_quote else None


async def collect_cell_rules(model_client, search_index, sources_by_id, target_area, rule_category):
    target_area = canonicalize_area(target_area)
    context_passages = retrieve_cell_context(search_index, sources_by_id, target_area, rule_category)
    cell_output = {
        "jurisdiction": target_area,
        "category": rule_category,
        "status": "silent",
        "rules": [],
        "finding": None,
        "rejected": [],
    }
    if not context_passages:
        return cell_output

    context_markup = "\n".join(
        f'<passage id="{context_id}" doc="{source_id}" source_type="{sources_by_id[source_id].source_type}">'
        f"\n{excerpt}\n</passage>"
        for context_id, source_id, _clean_offset, excerpt in context_passages
    )
    model_output = await model_client.call(
        step="cell",
        model=CELL_MODEL,
        system=prompt_templates.CELL_SYSTEM,
        schema=response_schemas.CELL,
        prompt=prompt_templates.CELL_HUMAN.format(
            jurisdiction=target_area, category=rule_category, passages=context_markup
        ),
        prompt_version=prompt_templates.PROMPT_VERSION,
        subject=f"{target_area}|{rule_category}",
    )
    cell_output["status"] = model_output["cell_status"]
    citations_by_id = {
        context_id: (source_id, excerpt)
        for context_id, source_id, _clean_offset, excerpt in context_passages
    }
    for rule_position, proposed_rule in enumerate(model_output["rules"], 1):
        verified_citation = _resolve_citation(
            sources_by_id, citations_by_id, proposed_rule.get("passage_id"), proposed_rule["quoted_span"]
        )
        if (
            canonicalize_area(proposed_rule["jurisdiction"]) != target_area
            or proposed_rule["category"] != rule_category
        ):
            rejection_reason = "rule outside the cell"
        elif verified_citation is None:
            rejection_reason = "quote not verified in cited passage and raw document"
        else:
            source_id, original_quote = verified_citation
            accepted_rule = {
                field_name: field_value
                for field_name, field_value in proposed_rule.items()
                if field_name != "passage_id"
            }
            accepted_rule.update(
                candidate_id=f"cell:{target_area}:{rule_category}:{rule_position}",
                source_doc_id=source_id,
                quoted_span=original_quote,
                jurisdiction=target_area,
                method="cell",
            )
            cell_output["rules"].append(accepted_rule)
            continue
        cell_output["rejected"].append({
            "cell": f"{target_area}|{rule_category}", "rule": proposed_rule, "reason": rejection_reason,
        })

    if model_output["cell_status"] == "no_rule_stated":
        verified_citation = _resolve_citation(
            sources_by_id, citations_by_id,
            model_output.get("no_rule_passage_id"), model_output.get("no_rule_quote"),
        )
        if verified_citation is not None:
            source_id, original_quote = verified_citation
            cell_output["finding"] = {
                "jurisdiction": target_area,
                "category": rule_category,
                "kind": "no_rule",
                "doc_id": source_id,
                "quoted_span": original_quote,
                "basis_citation": model_output.get("basis_citation"),
                "reason": "cell extraction: no rule stated",
                "method": "cell",
            }
    return cell_output


async def collect_all_cells(model_client, sources, guard_call=None):
    search_index = PassageIndex(sources)
    sources_by_id = {source.doc_id: source for source in sources}
    pending_cells = [
        (
            f"cell {target_area}|{rule_category}",
            collect_cell_rules(model_client, search_index, sources_by_id, target_area, rule_category),
        )
        for target_area in TARGET_AREAS
        for rule_category in response_schemas.CATEGORIES
    ]
    if guard_call is None:
        return await async_tasks.gather(*(pending_result for _task_label, pending_result in pending_cells))
    return await async_tasks.gather(*(
        guard_call(task_label, pending_result, None) for task_label, pending_result in pending_cells
    ))
