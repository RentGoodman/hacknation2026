from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
CACHE_DIR = ROOT / "extraction" / "cache" / "llm"
AUDIT_PATH = ROOT / "out" / "audit.jsonl"

EXTRACT_MODEL = "claude-sonnet-5-5"
REVIEW_MODEL = "claude-opus-5-5"


class CacheMiss(RuntimeError):
    pass


def cache_key(model: str, system: str, prompt: str, schema: dict) -> str:
    blob = "\x1f".join([model, system, prompt, json.dumps(schema, sort_keys=True)])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLM:
    def _step_down(self) -> None:
        if not self._stepped:
            self._stepped = True
            async def hold():
                for _ in range(max(0, self._concurrency - STEP_DOWN_TO)):
                    await self._sem.acquire()
            asyncio.get_running_loop().create_task(hold())

    def __init__(self, concurrency: int = 12, cache_dir: Path = CACHE_DIR, audit_path: Path = AUDIT_PATH,
                 offline: bool | None = None):
        self.cache_dir = cache_dir
        self.audit_path = audit_path
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.offline = (not os.environ.get("ANTHROPIC_API_KEY") and shutil.which("claude") is None) \
            if offline is None else offline
        self._sem = asyncio.Semaphore(concurrency)
        self._concurrency = concurrency
        self._stepped = False
        self._client = None
        self._audit_lock = asyncio.Lock()

    def _api(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(max_retries=4)
        return self._client

    async def call(self, *, step: str, model: str, system: str, prompt: str, schema: dict,
                   prompt_version: str, subject: str, doc_sha: str | None = None,
                   effort: str = "high", counts: dict | None = None) -> dict:
        key = cache_key(model, system, prompt, schema)
        path = self.cache_dir / key[:2] / f"{key}.json"
        t0 = time.monotonic()
        usage: dict[str, Any] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            result, hit = data["result"], True
            usage = data.get("usage", {})
        else:
            if self.offline:
                raise CacheMiss(f"{step}/{subject}: no cached response for {key} and no ANTHROPIC_API_KEY")
            async with self._sem:
                result, usage = await self._request(model, system, prompt, schema, effort)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "step": step, "subject": subject,
                                        "prompt_version": prompt_version, "usage": usage,
                                        "result": result}, ensure_ascii=False, indent=1), encoding="utf-8")
            hit = False
        await self._audit({
            "step": step, "subject": subject, "doc_sha256": doc_sha, "prompt_version": prompt_version,
            "model": model, "cache_key": key, "cache_hit": hit,
            "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
            "seconds": round(time.monotonic() - t0, 2), "counts": counts or _counts(result),
        })
        return result

    async def _request(self, model, system, prompt, schema, effort):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return await self._request_cli(model, system, prompt, schema)
        import jsonschema

        client = self._api()
        native = _union_count(schema) <= UNION_LIMIT
        sys_text = system if native else system + SCHEMA_INSTRUCTION + json.dumps(schema, sort_keys=True)
        output_config: dict[str, Any] = {"effort": effort}
        if native:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        last_err: Exception | None = None
        usage = {"input_tokens": 0, "output_tokens": 0}
        messages = [{"role": "user", "content": prompt}]
        for attempt in range(4):
            try:
                async with client.messages.stream(
                    model=model, max_tokens=64000,
                    system=[{"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}],
                    messages=messages,
                    output_config=output_config,
                ) as stream:
                    msg = await stream.get_final_message()
            except Exception as e:
                last_err = e
                if getattr(e, "status_code", None) in (429, 529) or "overloaded" in str(e).lower():
                    self._step_down()
                await asyncio.sleep(30 * (attempt + 1))
                continue
            u = msg.usage
            usage["input_tokens"] += u.input_tokens
            usage["output_tokens"] += u.output_tokens
            if msg.stop_reason in ("refusal", "max_tokens"):
                last_err = RuntimeError(f"model stopped with {msg.stop_reason}")
                continue
            text = "".join(b.text for b in msg.content if b.type == "text")
            try:
                body = _json_body(text)
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    from json_repair import repair_json

                    data = json.loads(repair_json(body))
                jsonschema.validate(data, schema)
                return data, usage
            except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                last_err = e
                messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": text},
                            {"role": "user", "content": "That reply does not validate against the required JSON "
                             f"schema: {str(e)[:600]}\nReply again with the corrected JSON object only."}]
        raise RuntimeError(f"no valid structured output: {str(last_err)[:300]}")

    async def _request_cli(self, model, system, prompt, schema):
        from llm.backend import complete_json

        alias = "opus" if "opus" in model else "sonnet"
        result = await asyncio.to_thread(
            complete_json, prompt, system=system, model=alias, schema=schema, max_retries=3
        )
        return result, {}

    def cached_result(self, key: str) -> dict:
        path = self.cache_dir / key[:2] / f"{key}.json"
        if not path.exists():
            raise CacheMiss(f"cached response {key} is missing")
        return json.loads(path.read_text(encoding="utf-8"))["result"]

    def cache_status(self, *, model: str, system: str, prompt: str, schema: dict) -> tuple[str, bool]:
        key = cache_key(model, system, prompt, schema)
        return key, (self.cache_dir / key[:2] / f"{key}.json").exists()

    async def _audit(self, row: dict) -> None:
        async with self._audit_lock:
            with self.audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


UNION_LIMIT = 16
STEP_DOWN_TO = 8
SCHEMA_INSTRUCTION = ("\n\nOutput format: reply with one JSON object only (no prose, no code fence) that validates "
                      "against this JSON schema. Every property is required; use null where the schema allows it.\n")


def _union_count(schema: Any) -> int:
    if isinstance(schema, dict):
        own = 1 if isinstance(schema.get("type"), list) or "anyOf" in schema else 0
        return own + sum(_union_count(v) for v in schema.values())
    if isinstance(schema, list):
        return sum(_union_count(v) for v in schema)
    return 0


def _json_body(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start >= 0 else text


UNION_LIMIT = 16
STEP_DOWN_TO = 8
SCHEMA_INSTRUCTION = ("\n\nOutput format: reply with one JSON object only (no prose, no code fence) that validates "
                      "against this JSON schema. Every property is required; use null where the schema allows it.\n")


def _union_count(schema: Any) -> int:
    if isinstance(schema, dict):
        own = 1 if isinstance(schema.get("type"), list) or "anyOf" in schema else 0
        return own + sum(_union_count(v) for v in schema.values())
    if isinstance(schema, list):
        return sum(_union_count(v) for v in schema)
    return 0


def _json_body(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start >= 0 else text


def _counts(result: Any) -> dict:
    if isinstance(result, dict):
        return {k: len(v) for k, v in result.items() if isinstance(v, list)}
    return {}
