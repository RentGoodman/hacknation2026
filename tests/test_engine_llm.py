import json
import subprocess

import pytest

from engine import classify_conditions as cc
from llm import backend


def ok(result):
    out = json.dumps({"type": "result", "is_error": False, "result": result})
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=out, stderr="")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy")
    monkeypatch.setattr(backend, "_semaphore", None)
    monkeypatch.setattr(backend, "_sleep", lambda s: None)


def test_ask_uses_the_cli_with_sonnet_and_labels_the_backend(monkeypatch):
    calls = []
    monkeypatch.setattr(backend.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)) or ok("reply"))
    assert cc._ask("classify this") == ("reply", "claude_cli:sonnet")
    cmd, kw = calls[0]
    assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--model") + 1] == "sonnet"
    assert "ANTHROPIC_API_KEY" not in kw["env"] and kw["input"] == "classify this"


def test_unparseable_reply_is_dropped_from_cache(monkeypatch):
    replies = [ok("no json here"), ok('{"conditions": [{"field": "exemptions", "effect": "informational", '
                                      '"label": "x"}]}')]
    monkeypatch.setattr(backend.subprocess, "run", lambda cmd, **kw: replies.pop(0))
    rule = {"team_rule_id": "r-0001", "title": "t", "requirement": "r"}
    texts = [("exemptions", "some exemption")]
    with pytest.raises(ValueError):
        cc._claude(rule, texts)
    conds, label = cc._claude(rule, texts)
    assert label == "claude_cli:sonnet" and conds[0]["effect"] == "informational"


def test_missing_cli_stops_calls_and_falls_back_to_heuristic(monkeypatch):
    calls = []

    def missing(cmd, **kw):
        calls.append(cmd)
        raise FileNotFoundError("claude")
    monkeypatch.setattr(backend.subprocess, "run", missing)
    monkeypatch.setattr(cc, "CACHE", cc.CACHE.parent / "does-not-exist.json")
    rules = [{"team_rule_id": f"r-{i}", "exemptions": "Owner-occupied buildings are exempt."} for i in range(2)]
    log, err = cc.classify(rules, use_cache=False)
    assert err and "LLM unavailable" in err
    assert all(e["classifier"].startswith("heuristic") for e in log)
    assert len(calls) == 1


def test_validity_uses_backend_and_stops_on_usage_limit(monkeypatch, tmp_path):
    from engine import validity
    monkeypatch.setattr(validity, "CACHE", tmp_path / "validity.json")
    limit = subprocess.CompletedProcess(args=[], returncode=1, stderr="",
                                        stdout=json.dumps({"is_error": True, "result": "Claude AI usage limit reached"}))
    calls = []
    monkeypatch.setattr(backend.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or limit)
    rules = [{"team_rule_id": f"r-{i}", "title": "Allowable increase", "requirement": "for July 1, 2025 through "
              "June 30, 2026"} for i in range(3)]
    log, err = validity.attach(rules, use_api=True)
    assert log == [] and err and "usage limit" in err.lower()
    assert len(calls) == 3


def test_validity_records_backend_label(monkeypatch, tmp_path):
    from engine import validity
    monkeypatch.setattr(validity, "CACHE", tmp_path / "validity.json")
    monkeypatch.setattr(backend.subprocess, "run", lambda cmd, **kw: ok(
        '{"kind": "figure_period", "end_date": "2026-06-30", "clause": "through June 30, 2026"}'))
    rule = {"team_rule_id": "r-1", "title": "Allowable increase", "requirement": "for July 1, 2025 through June 30, 2026"}
    log, err = validity.attach([rule], use_api=True)
    assert err is None and rule["figure_period_end"] == "2026-06-30"
    assert json.loads((tmp_path / "validity.json").read_text())[validity._key(rule)]["model"] == "claude_cli:sonnet"
