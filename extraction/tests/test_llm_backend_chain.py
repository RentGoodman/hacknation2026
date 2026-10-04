import asyncio
import json
import subprocess
import sys

import pytest

pytest.importorskip("langchain_core")

from extraction import llm as ellm
from extraction.link import PROMPT as LINK_PROMPT, LinkResult
from extraction.schema import ExtractionResult

backend = ellm._llm_backend()

INPUTS = {"query_date": "2026-10-01", "doc_id": "D001", "jurisdictions": "CA", "source_type": "official",
          "url": "https://example.org", "chunk_note": "", "text": "Some statute text."}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy")
    monkeypatch.setattr(backend, "_semaphore", None)
    monkeypatch.setattr(backend, "_sleep", lambda s: None)


def fake_run(*results, calls):
    replies = [subprocess.CompletedProcess(args=[], returncode=0, stderr="",
                                           stdout=json.dumps({"is_error": False, "result": r})) for r in results]

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return replies.pop(0)
    return run


def test_llm_backend_is_the_repo_root_module():
    assert backend.__file__.startswith(str(ellm.REPO_ROOT / "llm"))


@pytest.mark.parametrize("model, expected", [
    ("anthropic:claude-sonnet-5-5", "sonnet"), (ellm.DEFAULT_MODEL, "sonnet"), ("claude_cli:opus", "opus"),
    ("anthropic:claude-opus-5-5", "opus"), ("claude-haiku-4-5-20251001", "haiku"),
])
def test_claude_models_use_the_subscription_backend(model, expected, monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain.chat_models", None)
    assert ellm.build_model(model) == ellm.ClaudeBackendModel(expected)


def test_other_providers_still_use_langchain():
    assert not ellm.uses_backend("openai:gpt-5")
    assert not ellm.uses_backend("openrouter:anthropic/claude-sonnet-5.5")


def test_extraction_chain_sends_same_prompt_and_validates(monkeypatch):
    calls = []
    monkeypatch.setattr(backend.subprocess, "run", fake_run('```json\n{"rules": []}\n```', calls=calls))
    chain = ellm.structured_chain(ellm.PROMPT, ellm.build_model(ellm.DEFAULT_MODEL), ExtractionResult)
    result = chain.invoke(INPUTS)
    assert isinstance(result, ExtractionResult) and result.rules == []
    cmd, kw = calls[0]
    assert cmd[:6] == ["claude", "-p", "--output-format", "json", "--model", "sonnet"]
    assert cmd[cmd.index("--append-system-prompt") + 1] == ellm.SYSTEM_PROMPT
    system, user = ellm.render_messages(ellm.PROMPT, INPUTS)
    assert system == ellm.SYSTEM_PROMPT and kw["input"].startswith(user)
    assert '"ExtractedRule"' in kw["input"]
    assert "ANTHROPIC_API_KEY" not in kw["env"]


def test_invalid_reply_is_retried_and_async_works(monkeypatch):
    calls = []
    good = {"links": [{"governing": "R2", "yielding": "R1", "explanation": "x", "uncertain": False}], "conflicts": []}
    monkeypatch.setattr(backend.subprocess, "run", fake_run('{"links": "nope"}', json.dumps(good), calls=calls))
    chain = ellm.structured_chain(LINK_PROMPT, ellm.ClaudeBackendModel("sonnet"), LinkResult, retries=3)
    result = asyncio.run(chain.ainvoke({"query_date": "2026-10-01", "state": "CA", "category": "x", "rules": "R1: {}"}))
    assert isinstance(result, LinkResult) and result.links[0].governing == "R2"
    assert len(calls) == 2
