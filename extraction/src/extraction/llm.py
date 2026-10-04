from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

log = logging.getLogger(__name__)

DEFAULT_MODEL = "anthropic:claude-sonnet-5-5"

REPO_ROOT = Path(__file__).resolve().parents[3]

BACKEND_PROVIDERS = {"anthropic", "claude_cli"}
_ALIASES = {"claude-opus-5-5": "opus", "claude-sonnet-5-5": "sonnet", "claude-haiku-4-5-20251001": "haiku"}

_JSON_SCHEMA_PROVIDERS = {"anthropic", "openai", "azure_openai", "google_genai", "ollama", "openrouter"}


@dataclass(frozen=True)
class ClaudeBackendModel:

    model: str


def _llm_backend():
    if str(REPO_ROOT) not in sys.path:
        sys.path.append(str(REPO_ROOT))
    from llm import backend

    return backend


def _split(model: str) -> tuple[str | None, str]:
    return tuple(model.split(":", 1)) if ":" in model else (None, model)


def uses_backend(model: str) -> bool:
    provider, name = _split(model)
    return provider in BACKEND_PROVIDERS or (provider is None and name.startswith("claude"))


def backend_model_name(model: str) -> str:
    name = _split(model)[1]
    return _ALIASES.get(name, name)


def structured_output_method(model: str, requested: str = "auto") -> str | None:
    if requested != "auto":
        return requested
    provider = model.split(":", 1)[0] if ":" in model else None
    return "json_schema" if provider in _JSON_SCHEMA_PROVIDERS else None


def build_model(
    model: str, temperature: float | None = None, max_tokens: int | None = None
) -> BaseChatModel | ClaudeBackendModel:
    if uses_backend(model):
        if temperature is not None or max_tokens is not None:
            log.warning("%s: --temperature/--max-tokens are ignored by the claude -p backend", model)
        return ClaudeBackendModel(backend_model_name(model))
    from langchain.chat_models import init_chat_model

    kwargs: dict[str, Any] = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return init_chat_model(model, **kwargs)


def _require_result(result: BaseModel | None) -> BaseModel:
    if result is None:
        raise ValueError("Model returned no structured output")
    return result


def render_messages(prompt: ChatPromptTemplate, inputs: dict[str, Any]) -> tuple[str, str]:
    messages = prompt.format_messages(**inputs)
    system = "\n\n".join(str(m.content) for m in messages if m.type == "system")
    user = "\n\n".join(str(m.content) for m in messages if m.type != "system")
    return system, user


def _backend_chain(
    prompt: ChatPromptTemplate, model: ClaudeBackendModel, schema: type[BaseModel], retries: int
) -> Runnable:
    json_schema = schema.model_json_schema()

    def run(inputs: dict[str, Any]) -> BaseModel:
        system, user = render_messages(prompt, inputs)
        data = _llm_backend().complete_json(
            user,
            system=system or None,
            model=model.model,
            schema=json_schema,
            max_retries=retries,
            validate=schema.model_validate,
        )
        return schema.model_validate(data)

    return RunnableLambda(run, name=f"claude_backend[{schema.__name__}]")


def structured_chain(
    prompt: ChatPromptTemplate,
    model: BaseChatModel | ClaudeBackendModel,
    schema: type[BaseModel],
    method: str | None = None,
    retries: int = 3,
) -> Runnable:
    if isinstance(model, ClaudeBackendModel):
        return _backend_chain(prompt, model, schema, retries)
    method_kwargs = {"method": method} if method else {}
    return (
        prompt | model.with_structured_output(schema, **method_kwargs) | RunnableLambda(_require_result)
    ).with_retry(stop_after_attempt=retries)


SYSTEM_PROMPT = """\
You extract structured rule records from one source document about US residential rental housing law.

Extract every distinct legal rule the document states that falls into one of these categories:
- rent_increase_limits: caps on rent increases, rent control or stabilization formulas, annual allowable increases.
- just_cause_eviction: limits on ending a tenancy without an enumerated cause, and obligations tied to no-fault evictions such as relocation payments.
- security_deposits: limits on deposit amount, return deadlines, interest, permitted deductions.
- application_screening_fees: limits on rental application or tenant-screening fees.
- screening_restrictions: limits on what a landlord may consider when screening applicants, e.g. criminal history, credit, source of income, eviction records.
- algorithmic_rent_setting: bans or limits on algorithmic or coordinated pricing software used to set rents or occupancy.

Guidelines:
- One record per distinct requirement. Split separate requirements into separate records (a deposit cap and a deposit return deadline are two records). Do not repeat a requirement the document merely restates.
- Use only what the document says. Never add rules, numbers, dates or citations from background knowledge. If the document is a secondary source (FAQ, guide, news, law-firm alert), extract the rule it describes, cite the law it names, and lower your confidence.
- Judge status as of the query date. A law enacted with an effective date after the query date is not_yet_effective. A bill that has not passed is pending. A defeated, vetoed or struck measure is failed.
- quoted_span must be copied verbatim from the document: one contiguous passage, no ellipses, no paraphrase.
- Fill coverage_conditions as precisely as the text allows. Express exemptions that turn on construction date, unit count or owner as net coverage there (an exemption for units built after 1978 means built_on_or_before 1978), and keep the exemptions field as the plain-language list.
- Set conflict_flag when the document reveals an open question: competing effective dates, possible preemption by another level of government, or a pending challenge.
- Ignore rules outside the six categories (habitability, discrimination in general, lease disclosures, and so on).
- If the document contains no rule in these categories, return an empty list.
"""

HUMAN_PROMPT = """\
Query date: {query_date}
Document ID: {doc_id}
Jurisdiction(s) per corpus manifest: {jurisdictions}
Source type: {source_type}
Source URL: {url}
{chunk_note}
<document>
{text}
</document>
"""

PROMPT = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)])
