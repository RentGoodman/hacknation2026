from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_PATH = REPO_ROOT / "out" / "audit.jsonl"
CACHE_DIR = REPO_ROOT / "extraction" / "out" / "llm_cache"
DEFAULT_CONCURRENCY = 10

_audit_lock = asyncio.Lock()


def prompt_hash(model_name: str, schema: type[BaseModel], prompt: ChatPromptTemplate, inputs: dict[str, Any]) -> str:
    rendered = "\n\n".join(f"[{m.type}]\n{m.content}" for m in prompt.format_messages(**inputs))
    payload = json.dumps({"model": model_name, "schema": schema.__name__, "prompt": rendered}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _log(entry: dict[str, Any]) -> None:
    async with _audit_lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class AuditedChain:

    def __init__(
        self,
        chain: Runnable | None,
        prompt: ChatPromptTemplate,
        schema: type[BaseModel],
        model_name: str,
        purpose: str,
        cache_dir: Path = CACHE_DIR,
        replay: Any = None,
    ):
        self.chain = chain
        self.prompt = prompt
        self.schema = schema
        self.model_name = model_name
        self.purpose = purpose
        self.cache_dir = cache_dir
        self.replay = replay

    async def ainvoke(self, inputs: dict[str, Any], context: dict[str, Any] | None = None) -> BaseModel:
        h = prompt_hash(self.model_name, self.schema, self.prompt, inputs)
        path = self.cache_dir / f"{h}.json"
        hit = path.exists()
        if hit:
            raw = path.read_text(encoding="utf-8")
            result = self.schema.model_validate_json(raw)
        else:
            if self.replay is not None:
                result = self.replay(inputs)
            else:
                result = await self.chain.ainvoke(inputs)
            raw = result.model_dump_json()
            if self.replay is None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(raw, encoding="utf-8")
        await _log(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "prompt_hash": h,
                "model": self.model_name,
                "cache_hit": hit,
                "purpose": self.purpose,
                **(context or {}),
                "raw_output": json.loads(raw),
            }
        )
        return result
