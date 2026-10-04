import json
import subprocess

import pytest

from llm import backend


class FakeRun:

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, **kwargs})
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def ok(result, returncode=0, is_error=False, stderr=""):
    out = json.dumps({"type": "result", "subtype": "success", "is_error": is_error, "result": result})
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=out, stderr=stderr)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setattr(backend, "_semaphore", None)
    sleeps = []
    monkeypatch.setattr(backend, "_sleep", sleeps.append)
    return sleeps


def test_api_keys_never_reach_the_cli(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-dummy")
    fake = FakeRun(ok("hello"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    assert backend.complete("hi", model="sonnet") == "hello"
    call = fake.calls[0]
    assert "ANTHROPIC_API_KEY" not in call["env"]
    assert "ANTHROPIC_AUTH_TOKEN" not in call["env"]
    assert "test-dummy" not in call["env"].values()
    assert call["cmd"] == ["claude", "-p", "--output-format", "json", "--model", "sonnet"]
    assert call["input"] == "hi" and call["text"] is True and call["capture_output"] is True


def test_second_identical_call_is_served_from_cache(monkeypatch, tmp_path):
    fake = FakeRun(ok("first"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    assert backend.complete("same prompt", system="sys", model="sonnet") == "first"
    assert backend.complete("same prompt", system="sys", model="sonnet") == "first"
    assert len(fake.calls) == 1
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_cache_key_depends_on_model_system_and_prompt(monkeypatch):
    fake = FakeRun(ok("a"), ok("b"), ok("c"), ok("d"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    backend.complete("p", model="sonnet")
    backend.complete("p", model="opus")
    backend.complete("p", system="s", model="sonnet")
    backend.complete("p2", model="sonnet")
    assert len(fake.calls) == 4
    assert backend.cache_key("b", "a", "m") != backend.cache_key("", "ab", "m")


def test_cache_applies_to_api_backend_too(monkeypatch):
    fake = FakeRun(ok("cached"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    backend.complete("p", model="sonnet")
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setattr(backend, "_call_api", lambda *a: pytest.fail("cache hit must not call the API"))
    assert backend.complete("p", model="sonnet") == "cached"


@pytest.mark.parametrize("value, expected", [
    (None, "claude_cli"), ("", "claude_cli"), ("claude_cli", "claude_cli"), ("API_", "claude_cli"),
    ("API", "claude_cli"), (" api", "claude_cli"), ("api", "api"),
])
def test_api_backend_only_with_llm_backend_api(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("LLM_BACKEND", raising=False)
    else:
        monkeypatch.setenv("LLM_BACKEND", value)
    assert backend._select_backend() == expected


def test_default_call_uses_cli_even_with_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy")
    monkeypatch.setattr(backend, "_call_api", lambda *a: pytest.fail("api backend selected without LLM_BACKEND=api"))
    fake = FakeRun(ok("via cli"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    assert backend.complete("x") == "via cli"
    assert fake.calls[0]["cmd"][-2:] == ["--model", "opus"]


def test_retry_after_failure_then_success(monkeypatch, isolated):
    fake = FakeRun(ok("boom", returncode=1, is_error=True), subprocess.TimeoutExpired("claude", 5), ok("fine"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    assert backend.complete("p", model="sonnet", max_retries=3) == "fine"
    assert len(fake.calls) == 3
    assert len(isolated) == 2 and 2 <= isolated[0] < 3 and 4 <= isolated[1] < 5


def test_usage_limit_uses_longer_backoff_and_raises_after_max_retries(monkeypatch, isolated):
    limit = ok("Claude AI usage limit reached|1760000000", returncode=1, is_error=True)
    fake = FakeRun(limit, limit)
    monkeypatch.setattr(backend.subprocess, "run", fake)
    with pytest.raises(backend.LLMRateLimitError, match="usage limit"):
        backend.complete("p", model="sonnet", max_retries=2)
    assert len(fake.calls) == 2
    assert len(isolated) == 1 and isolated[0] >= backend.USAGE_LIMIT_BACKOFF_BASE


def test_is_error_reply_is_not_cached(monkeypatch):
    fake = FakeRun(ok("API Error: 529 overloaded", is_error=True), ok("good"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    assert backend.complete("p", model="sonnet", max_retries=2) == "good"
    assert backend.complete("p", model="sonnet") == "good"
    assert len(fake.calls) == 2


def test_missing_cli_is_not_retried(monkeypatch, isolated):
    fake = FakeRun(FileNotFoundError("claude"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    with pytest.raises(backend.LLMUnavailableError, match="LLM unavailable"):
        backend.complete("p")
    assert len(fake.calls) == 1 and not isolated


def test_system_prompt_is_appended(monkeypatch):
    fake = FakeRun(ok("a"), ok("b"))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    backend.complete("user text", system="You are terse.", model="haiku")
    backend.complete("user text", model="haiku")
    assert fake.calls[0]["cmd"] == ["claude", "-p", "--output-format", "json", "--model", "haiku",
                                    "--append-system-prompt", "You are terse."]
    assert "--append-system-prompt" not in fake.calls[1]["cmd"]
    assert fake.calls[0]["input"] == "user text"


def test_concurrency_cap_from_env(monkeypatch):
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "2")
    sem = backend._get_semaphore()
    assert sem.acquire(blocking=False) and sem.acquire(blocking=False)
    assert not sem.acquire(blocking=False)
    sem.release()
    sem.release()


def test_complete_json_adds_schema_and_parses_fences(monkeypatch):
    fake = FakeRun(ok('Here:\n```json\n{"a": 1}\n```'))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    assert backend.complete_json("give a", model="sonnet", schema=schema) == {"a": 1}
    sent = fake.calls[0]["input"]
    assert sent.startswith("give a") and "JSON schema" in sent and '"integer"' in sent


def test_complete_json_drops_bad_reply_from_cache_and_retries(monkeypatch):
    fake = FakeRun(ok("not json at all"), ok('{"a": 2}'))
    monkeypatch.setattr(backend.subprocess, "run", fake)
    assert backend.complete_json("p", model="sonnet") == {"a": 2}
    assert len(fake.calls) == 2


def test_api_backend_maps_aliases(monkeypatch):
    seen = {}

    class Msg:
        content = [type("B", (), {"type": "text", "text": "api reply"})()]

    class Messages:
        def create(self, **kw):
            seen.update(kw)
            return Msg()

    class Client:
        messages = Messages()

    import types
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda: Client()))
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy")
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **k: pytest.fail("cli used with LLM_BACKEND=api"))
    assert backend.complete("p", system="s", model="sonnet") == "api reply"
    assert seen["model"] == "claude-sonnet-5-5" and seen["system"] == "s"
