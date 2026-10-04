import asyncio
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from extraction.v3 import cells, schemas
from extraction.v3.bm25 import PASSAGE, Index
from extraction.v3.loader import Doc, load


def _doc(doc_id, text, jurisdiction="CA", source_type="official"):
    return Doc(doc_id, jurisdiction, "https://example.test", source_type, "", text, text=text)


def _select(docs, jurisdiction="CA", category="security_deposits"):
    return cells.retrieve_cell_context(Index(docs), {d.doc_id: d for d in docs}, jurisdiction, category)


@pytest.mark.parametrize("category,text", [
    ("rent_increase_limits", "The permissible ceiling tracks inflation."),
    ("just_cause_eviction", "Reprisal and retaliation are prohibited."),
    ("security_deposits", "Deductions require an itemized statement for cleaning and damage."),
    ("application_screening_fees", "Brokerage commissions and nonrefundable fees are prohibited."),
    ("screening_restrictions", "Applicants receiving vouchers may not be denied housing."),
    ("algorithmic_rent_setting", "Sharing nonpublic information through algorithms is prohibited."),
])
def test_queries_find_word_forms_and_category_specific_vocabulary(category, text):
    passages = _select([_doc("D001", text)], category=category)
    assert [p[3] for p in passages] == [text]


def test_a_place_name_alone_does_not_retrieve_a_passage():
    docs = [
        _doc("D001", "Berkeley Berkeley Berkeley parks and recreation.", "Berkeley, CA"),
        _doc("D002", "Security deposits earn interest.", "Berkeley, CA"),
    ]
    assert [p[1] for p in _select(docs, "Berkeley, CA")] == ["D002"]


def test_state_names_boost_category_matches_in_other_jurisdictions_documents():
    docs = [
        _doc("D001", "Security deposits elsewhere.", "NJ"),
        _doc("D002", "Security deposits California.", "NJ"),
    ]
    assert _select(docs)[0][1] == "D002"


def test_jurisdiction_boost_normalizes_input_and_each_manifest_jurisdiction():
    docs = [
        _doc("D001", "Security deposits earn interest.", "NJ"),
        _doc("D002", "Security deposits earn interest.", "MA; California; "),
    ]
    assert _select(docs, "California")[0][1] == "D002"


def test_starter_reservation_excludes_supplemental_official_documents():
    docs = [
        _doc(f"DX{n:02}", "Security deposits earn interest and require itemized receipts.")
        for n in range(10)
    ] + [
        _doc("D001", "deposit".ljust(PASSAGE) * 3),
        _doc("D002", "deposit".ljust(PASSAGE) * 3),
    ]
    passages = _select(docs)
    assert len(passages) == 10
    assert Counter(p[1] for p in passages[:6]) == {"D001": 3, "D002": 3}
    assert all(p[1].startswith("DX") for p in passages[6:])


@pytest.mark.parametrize("starter_count", [0, 1])
def test_unused_starter_slots_are_filled_from_other_sources(starter_count):
    docs = [_doc(f"D{n:03}", "Security deposits earn interest.") for n in range(starter_count)]
    docs += [
        _doc(f"X{n:02}", "Security deposits earn interest.", source_type="secondary")
        for n in range(12)
    ]
    assert len(_select(docs)) == 10


def test_equal_scores_are_stable_and_obey_the_per_document_limit():
    docs = [_doc(f"D{n:03}", "deposit".ljust(PASSAGE) * 5) for n in range(4)]
    passages = _select(docs)
    assert passages == _select(docs)
    assert [p[0] for p in passages] == [f"p{n}" for n in range(1, 11)]
    assert len({(p[1], p[2]) for p in passages}) == 10
    assert max(Counter(p[1] for p in passages).values()) == 3
    assert [p[2] for p in passages if p[1] == "D000"] == [0, PASSAGE, 2 * PASSAGE]


@pytest.fixture(scope="module")
def corpus():
    docs, _ = load()
    return Index(docs), {d.doc_id: d for d in docs}


@pytest.mark.parametrize("jurisdiction,category,expected_doc", [
    ("CA", "rent_increase_limits", "D024"),
    ("CA", "just_cause_eviction", "D023"),
    ("CA", "security_deposits", "D025"),
    ("CA", "application_screening_fees", "D026"),
    ("CA", "screening_restrictions", "D016"),
    ("Berkeley, CA", "algorithmic_rent_setting", "D001"),
    ("Hoboken, NJ", "rent_increase_limits", "DX20"),
])
def test_queries_retrieve_core_sources_from_the_corpus(corpus, jurisdiction, category, expected_doc):
    index, by_id = corpus
    passages = cells.retrieve_cell_context(index, by_id, jurisdiction, category)
    assert expected_doc in {p[1] for p in passages}


@pytest.fixture
def cited_cell(monkeypatch):
    first = "A security deposit may not exceed one month’s rent."
    second = "Landlords must pay deposit interest."
    doc = _doc("D001", first + "\n" + second)
    passages = [("p1", doc.doc_id, 0, first), ("p2", doc.doc_id, len(first) + 1, second)]
    monkeypatch.setattr(cells, "retrieve_cell_context", lambda *args: passages)
    return doc, first, second


def _extract(doc, response, jurisdiction="CA", category="security_deposits"):
    llm = SimpleNamespace(call=AsyncMock(return_value=response))
    result = asyncio.run(cells.collect_cell_rules(llm, Index([doc]), {doc.doc_id: doc}, jurisdiction, category))
    return result, llm.call


def _rule(**overrides):
    return {
        "jurisdiction": "California",
        "category": "security_deposits",
        "passage_id": "p1",
        "quoted_span": "A security deposit may not exceed one month's rent.",
        **overrides,
    }


def test_extraction_keeps_raw_quotes_and_canonical_candidate_ids(cited_cell):
    doc, first, _ = cited_cell
    rule = _rule()
    result, call = _extract(doc, {"cell_status": "rules_found", "rules": [rule]}, "California")
    assert result["rules"] == [{
        "jurisdiction": "CA",
        "category": "security_deposits",
        "quoted_span": first,
        "candidate_id": "cell:CA:security_deposits:1",
        "source_doc_id": "D001",
        "method": "cell",
    }]
    assert result["rejected"] == []
    assert rule == _rule()
    assert call.await_args.kwargs["subject"] == "CA|security_deposits"
    assert first in call.await_args.kwargs["prompt"]


@pytest.mark.parametrize("overrides", [
    {"passage_id": "missing"},
    {"quoted_span": "This quotation is invented."},
    {"quoted_span": "Landlords must pay deposit interest."},
    {"jurisdiction": "NJ"},
    {"category": "rent_increase_limits"},
])
def test_extraction_rejects_wrong_passages_quotes_and_cells(cited_cell, overrides):
    doc, _, _ = cited_cell
    rule = _rule(**overrides)
    result, _ = _extract(doc, {"cell_status": "rules_found", "rules": [rule]})
    assert result["rules"] == []
    assert result["rejected"][0]["rule"] == rule


def test_extraction_requires_a_quote_in_the_raw_document_too(cited_cell):
    doc, _, _ = cited_cell
    doc.raw = "Different text in the raw source."
    result, _ = _extract(doc, {"cell_status": "rules_found", "rules": [_rule()]})
    assert result["rules"] == []
    assert len(result["rejected"]) == 1


@pytest.mark.parametrize("passage_id,accepted", [("p1", True), ("missing", False), ("p2", False)])
def test_no_rule_findings_require_the_cited_passage(monkeypatch, passage_id, accepted):
    quote = "No local screening fee rule is stated."
    other = "Another paragraph."
    doc = _doc("D001", quote + "\n" + other)
    monkeypatch.setattr(cells, "retrieve_cell_context", lambda *args: [
        ("p1", "D001", 0, quote), ("p2", "D001", len(quote) + 1, other),
    ])
    response = {
        "cell_status": "no_rule_stated", "rules": [], "no_rule_quote": quote,
        "no_rule_passage_id": passage_id, "basis_citation": None,
    }
    result, _ = _extract(doc, response, category="application_screening_fees")
    assert (result["finding"] is not None) is accepted
    if accepted:
        assert result["finding"]["quoted_span"] == quote
        assert result["finding"]["doc_id"] == "D001"


def test_empty_retrieval_is_silent_without_a_model_call():
    doc = _doc("D001", "California parks and recreation.")
    result, call = _extract(doc, None)
    call.assert_not_awaited()
    assert result == {
        "jurisdiction": "CA", "category": "security_deposits", "status": "silent",
        "rules": [], "finding": None, "rejected": [],
    }


def test_collect_all_cells_preserves_order_and_safe_failure_handling(monkeypatch):
    monkeypatch.setattr(cells, "TARGET_AREAS", ["CA", "NJ"])

    async def extract(llm, index, docs_by_id, jur, cat):
        if (jur, cat) == ("NJ", "security_deposits"):
            raise RuntimeError("model failed")
        return {"jurisdiction": jur, "category": cat}

    failures = []

    async def safe(label, call, default):
        try:
            return await call
        except RuntimeError:
            failures.append(label)
            return default

    monkeypatch.setattr(cells, "collect_cell_rules", extract)
    results = asyncio.run(cells.collect_all_cells(None, [], safe))
    expected = [(jur, cat) for jur in ["CA", "NJ"] for cat in schemas.CATEGORIES]
    assert len(results) == len(expected)
    for result, (jur, cat) in zip(results, expected):
        if (jur, cat) == ("NJ", "security_deposits"):
            assert result is None
        else:
            assert result == {"jurisdiction": jur, "category": cat}
    assert failures == ["cell NJ|security_deposits"]
