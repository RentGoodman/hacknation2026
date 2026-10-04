from extraction.v3 import pipeline
from extraction.v3.client import cache_key
from extraction.v3 import prompts as P
from extraction.v3 import schemas as S


def test_existing_document_prompt_and_cache_contract_stay_v10():
    assert P.PROMPT_VERSION == "v10"
    assert "key_value is mandatory whenever" in P.EXTRACT_SYSTEM
    assert "main obligation or prohibition" not in P.EXTRACT_SYSTEM
    assert "D001" not in pipeline.NEW_PROMPT_DOC_IDS


def test_new_document_profile_is_explicit_and_has_a_distinct_cache_key():
    assert pipeline.NEW_PROMPT_DOC_IDS == {"DX20", "DX21"}
    assert pipeline.INCREMENTAL_CATEGORY_SCOPE["DX20"] == {"rent_increase_limits"}
    assert pipeline.INCREMENTAL_CATEGORY_SCOPE["DX21"] == {"rent_increase_limits"}
    assert P.NEW_DOCUMENT_PROMPT_VERSION == "v11-new-documents"
    assert "main obligation or prohibition" in P.NEW_DOCUMENT_EXTRACT_SYSTEM
    prompt = "same document payload"
    assert cache_key("model", P.EXTRACT_SYSTEM, prompt, S.EXTRACTION) != cache_key(
        "model", P.NEW_DOCUMENT_EXTRACT_SYSTEM, prompt, S.EXTRACTION
    )
