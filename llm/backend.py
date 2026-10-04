from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / ".llm_cache"
DEFAULT_MAX_CONCURRENCY = 3
DEFAULT_CLI_TIMEOUT = 900.0
DEFAULT_API_MAX_TOKENS = 16000
CLI = "claude"

API_MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-4-5-20251001"}

STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

LIMIT_MARKERS = ("usage limit", "rate limit", "limit reached", "overloaded", "429", "529")
USAGE_LIMIT_MARKERS = ("usage limit", "limit reached")
BACKOFF_BASE = 2.0
USAGE_LIMIT_BACKOFF_BASE = 60.0
MAX_DETAIL = 300

_sleep = time.sleep

_semaphore: threading.BoundedSemaphore | None = None
_semaphore_lock = threading.Lock()


class LLMError(RuntimeError):
    pass


class LLMRateLimitError(LLMError):

    def __init__(self, message: str, usage_limit: bool = False):
        super().__init__(message)
        self.usage_limit = usage_limit


class LLMUnavailableError(LLMError):
    pass



def _select_backend() -> str:
    return "api" if os.environ.get("LLM_BACKEND") == "api" else "claude_cli"


def backend_label(model: str) -> str:
    return f"{_select_backend()}:{model}"



def _cache_dir() -> Path:
    return Path(os.environ.get("LLM_CACHE_DIR") or DEFAULT_CACHE_DIR)


def cache_key(prompt: str, system: str | None, model: str) -> str:
    return hashlib.sha256("\x00".join((model, system or "", prompt)).encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def _cache_read(key: str) -> str | None:
    try:
        data = json.loads(_cache_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    result = data.get("result") if isinstance(data, dict) else None
    return result if isinstance(result, str) else None


def _cache_write(key: str, entry: dict[str, Any]) -> None:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=f".{key}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _cache_path(key))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def forget(prompt: str, system: str | None = None, model: str = "opus") -> None:
    try:
        _cache_path(cache_key(prompt, system, model)).unlink()
    except FileNotFoundError:
        pass



def _get_semaphore() -> threading.BoundedSemaphore:
    global _semaphore
    with _semaphore_lock:
        if _semaphore is None:
            try:
                n = int(os.environ.get("LLM_MAX_CONCURRENCY") or DEFAULT_MAX_CONCURRENCY)
            except ValueError:
                n = DEFAULT_MAX_CONCURRENCY
            _semaphore = threading.BoundedSemaphore(max(1, n))
        return _semaphore



def _truncate(text: str | None, n: int = MAX_DETAIL) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + "..."


def _limit_kind(text: str) -> tuple[bool, bool]:
    t = (text or "").lower()
    return any(m in t for m in LIMIT_MARKERS), any(m in t for m in USAGE_LIMIT_MARKERS)


def _cli_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in STRIPPED_ENV}


def _cli_timeout() -> float:
    try:
        return float(os.environ.get("LLM_CLI_TIMEOUT") or DEFAULT_CLI_TIMEOUT)
    except ValueError:
        return DEFAULT_CLI_TIMEOUT


def _call_cli(prompt: str, system: str | None, model: str) -> str:
    cmd = [CLI, "-p", "--output-format", "json", "--model", model]
    if system:
        cmd += ["--append-system-prompt", system]
    try:
        proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, env=_cli_env(), timeout=_cli_timeout())
    except FileNotFoundError as e:
        raise LLMUnavailableError(
            "LLM unavailable: `claude` CLI not found on PATH (install Claude Code and log in with `claude`, "
            "or set LLM_BACKEND=api to use the paid API)") from e
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"claude CLI timed out after {e.timeout:.0f}s") from e

    data: Any = None
    try:
        data = json.loads(proc.stdout) if proc.stdout.strip() else None
    except ValueError:
        data = None
    if isinstance(data, list):
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("type") == "result"), None)
    result = data.get("result") if isinstance(data, dict) else None
    is_error = bool(data.get("is_error")) if isinstance(data, dict) else False

    if proc.returncode != 0 or is_error or not isinstance(result, str):
        detail = _truncate(result if isinstance(result, str) else proc.stdout) or "(no output)"
        err = _truncate(proc.stderr)
        msg = f"claude CLI failed (exit {proc.returncode}): {detail}" + (f" | stderr: {err}" if err else "")
        limit, usage = _limit_kind(f"{result or ''} {proc.stdout if data is None else ''} {proc.stderr}")
        if limit:
            raise LLMRateLimitError(msg, usage_limit=usage)
        raise LLMError(msg)
    return result


def _call_api(prompt: str, system: str | None, model: str) -> str:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise LLMUnavailableError("LLM unavailable: LLM_BACKEND=api but ANTHROPIC_API_KEY is not set")
    try:
        import anthropic
    except ImportError as e:
        raise LLMUnavailableError("LLM unavailable: LLM_BACKEND=api needs the `anthropic` package") from e
    try:
        max_tokens = int(os.environ.get("LLM_API_MAX_TOKENS") or DEFAULT_API_MAX_TOKENS)
    except ValueError:
        max_tokens = DEFAULT_API_MAX_TOKENS
    kwargs: dict[str, Any] = {"model": API_MODELS.get(model, model), "max_tokens": max_tokens,
                              "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    try:
        msg = anthropic.Anthropic().messages.create(**kwargs)
    except Exception as e:
        text = f"{type(e).__name__}: {_truncate(str(e))}"
        limit, usage = _limit_kind(text)
        if limit or getattr(e, "status_code", None) in (429, 529):
            raise LLMRateLimitError(f"Anthropic API rate limit: {text}", usage_limit=usage) from e
        raise LLMError(f"Anthropic API call failed: {text}") from e
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")



def _backoff(attempt: int, usage_limit: bool) -> float:
    base = USAGE_LIMIT_BACKOFF_BASE if usage_limit else BACKOFF_BASE
    return base * (2 ** attempt) + random.uniform(0, 1)


def complete(prompt: str, system: str | None = None, model: str = "opus", max_retries: int = 3) -> str:
    key = cache_key(prompt, system, model)
    cached = _cache_read(key)
    if cached is not None:
        return cached

    backend = _select_backend()
    call: Callable[[str, str | None, str], str] = _call_api if backend == "api" else _call_cli
    attempts = max(1, max_retries)
    last: LLMError | None = None
    for attempt in range(attempts):
        try:
            with _get_semaphore():
                text = call(prompt, system, model)
        except LLMUnavailableError:
            raise
        except LLMError as e:
            last = e
            if attempt + 1 < attempts:
                _sleep(_backoff(attempt, isinstance(e, LLMRateLimitError) and e.usage_limit))
            continue
        _cache_write(key, {"backend": backend, "model": model, "result": text,
                           "created": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return text

    prefix = "rate/usage limit" if isinstance(last, LLMRateLimitError) else "LLM call failed"
    exc_type = LLMRateLimitError if isinstance(last, LLMRateLimitError) else LLMError
    err = exc_type(f"{prefix} after {attempts} attempt(s) ({backend}:{model}): {last}")
    raise err from last


JSON_INSTRUCTION = """

Respond with only a JSON object that conforms to the JSON schema below: no prose, no explanation, no code fences.

JSON schema:
{schema}"""

_FENCE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)```", re.S)


def extract_json(text: str) -> Any:
    candidates = [text.strip()] + [m.group(1).strip() for m in _FENCE.finditer(text)]
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{"): text.rindex("}") + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except ValueError:
            continue
    raise ValueError(f"no JSON object in model reply: {_truncate(text, 120)!r}")


def complete_json(prompt: str, system: str | None = None, model: str = "opus", schema: dict | None = None,
                  max_retries: int = 3, validate: Callable[[dict], Any] | None = None) -> dict:
    full = prompt + JSON_INSTRUCTION.format(schema=json.dumps(schema, indent=2)) if schema is not None else prompt
    attempts = max(1, max_retries)
    for attempt in range(attempts):
        text = complete(full, system=system, model=model, max_retries=max_retries)
        try:
            data = extract_json(text)
            if not isinstance(data, dict):
                raise ValueError(f"expected a JSON object, got {type(data).__name__}")
            if validate is not None:
                validate(data)
            return data
        except ValueError as e:
            forget(full, system, model)
            if attempt + 1 >= attempts:
                raise LLMError(f"invalid JSON reply after {attempts} attempt(s) ({model}): {_truncate(str(e))}") from e
    raise AssertionError("unreachable")
