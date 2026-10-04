from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .llm import structured_chain
from .schema import RuleRecord

log = logging.getLogger(__name__)


class RuleLink(BaseModel):
    governing: str = Field(description="Label of the rule that governs where both would apply, e.g. 'R3'.")
    yielding: str = Field(description="Label of the rule that yields to it, e.g. 'R1'.")
    explanation: str = Field(description="One sentence on why, citing the field that says so.")
    uncertain: bool = Field(
        description=(
            "True if it is legally uncertain whether this relationship holds, e.g. preemption that is "
            "argued but not settled, or depends on a law that is not yet effective."
        )
    )


class RuleConflict(BaseModel):
    rules: list[str] = Field(description="Labels of the rules involved, e.g. ['R2', 'R5'].")
    note: str = Field(description="What a human reviewer needs to resolve.")


class LinkResult(BaseModel):
    links: list[RuleLink] = Field(description="Every governs/yields relationship between rules in the group.")
    conflicts: list[RuleConflict] = Field(
        description="Disagreements between rules that a human should review. Empty if none."
    )


SYSTEM_PROMPT = """\
You are given rental housing rules from one US state and one category, extracted from different source documents. Decide how they interact.

Report a link when one rule governs and the other yields for the units both would cover. Typical cases:
- A stricter local rent-control or just-cause ordinance governs, and the statewide rule yields where the local rule applies (e.g. California's statewide rent cap exempts units under stricter local rent control).
- A state law preempts a local ordinance.
- An amended or newer version of a rule governs the older version.

Do not link rules that simply apply side by side (a deposit cap and a deposit return deadline), or two records that describe the same rule from different sources.

Report a conflict when rules disagree in a way a human should review: different numbers or effective dates for what appears to be the same rule, possible preemption that is not settled, or a law that is not yet effective that would displace one now in force.

Base every link and conflict on the records' own fields, especially interaction, exemptions, coverage_conditions, status and effective_date. Never invent a relationship the records don't support. Refer to rules only by their labels.
"""

HUMAN_PROMPT = """\
Query date: {query_date}
State: {state}
Category: {category}

Rules:
{rules}
"""

PROMPT = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)])

_FINGERPRINT_EXCLUDE = {"team_rule_id", "overrides"}


def rule_key(record: RuleRecord) -> str:
    digest = hashlib.sha1(f"{record.category}\n{record.quoted_span}".encode()).hexdigest()[:12]
    return f"{record.source_doc_id}:{digest}"


def _state(record: RuleRecord) -> str:
    return record.jurisdiction[-2:]


def group_rules(records: list[RuleRecord]) -> dict[str, list[RuleRecord]]:
    groups: dict[str, list[RuleRecord]] = defaultdict(list)
    for record in records:
        groups[f"{_state(record)}/{record.category}"].append(record)
    return {key: sorted(group, key=rule_key) for key, group in groups.items() if len(group) > 1}


def _fingerprint(group: list[RuleRecord], query_date: str) -> str:
    payload = [r.model_dump(mode="json", exclude=_FINGERPRINT_EXCLUDE) for r in group]
    return hashlib.sha1(json.dumps([query_date, payload], sort_keys=True).encode()).hexdigest()


def _render(group: list[RuleRecord]) -> str:
    fields = (
        "jurisdiction level status effective_date title requirement key_value coverage_conditions "
        "exemptions interaction citation source_doc_id"
    ).split()
    return "\n".join(
        f"R{i}: " + json.dumps(r.model_dump(mode="json", include=set(fields)), ensure_ascii=False)
        for i, r in enumerate(group, start=1)
    )


class Linker:
    def __init__(
        self,
        model: BaseChatModel,
        model_name: str,
        query_date: str,
        concurrency: int = 4,
        retries: int = 3,
        structured_method: str | None = None,
    ):
        self.model_name = model_name
        self.query_date = query_date
        self.chain = structured_chain(PROMPT, model, LinkResult, structured_method, retries)
        self._semaphore = asyncio.Semaphore(concurrency)

    async def link_group(self, group_key: str, group: list[RuleRecord]) -> dict[str, Any]:
        state, category = group_key.split("/", 1)
        async with self._semaphore:
            result: LinkResult = await self.chain.ainvoke(
                {"query_date": self.query_date, "state": state, "category": category, "rules": _render(group)}
            )

        keys = {f"R{i}": rule_key(r) for i, r in enumerate(group, start=1)}
        links = [
            {
                "governing": keys[link.governing],
                "yielding": keys[link.yielding],
                "explanation": link.explanation,
                "uncertain": link.uncertain,
            }
            for link in result.links
            if link.governing in keys and link.yielding in keys and link.governing != link.yielding
        ]
        conflicts = [
            {"rules": [keys[label] for label in c.rules if label in keys], "note": c.note}
            for c in result.conflicts
        ]
        dropped = len(result.links) - len(links)
        if dropped:
            log.warning("%s: dropped %d link(s) with unknown rule labels", group_key, dropped)
        return {
            "fingerprint": _fingerprint(group, self.query_date),
            "model": self.model_name,
            "links": links,
            "conflicts": [c for c in conflicts if c["rules"]],
        }


def stale_groups(
    groups: dict[str, list[RuleRecord]], cache: dict[str, Any], query_date: str
) -> dict[str, list[RuleRecord]]:
    return {
        key: group
        for key, group in groups.items()
        if cache.get(key, {}).get("fingerprint") != _fingerprint(group, query_date)
    }


async def link_all(
    linker: Linker, groups: dict[str, list[RuleRecord]], cache: dict[str, Any]
) -> tuple[dict[str, Any], int]:

    async def run(key: str, group: list[RuleRecord]) -> tuple[str, dict[str, Any] | None]:
        try:
            entry = await linker.link_group(key, group)
        except Exception:
            log.exception("%s: linking failed", key)
            return key, None
        log.info("%s: %d link(s), %d conflict(s)", key, len(entry["links"]), len(entry["conflicts"]))
        return key, entry

    results = await asyncio.gather(*(run(k, g) for k, g in groups.items()))
    cache = dict(cache)
    for key, entry in results:
        if entry is not None:
            cache[key] = entry
    return cache, sum(entry is None for _, entry in results)


def _append(existing: str | None, addition: str) -> str:
    return f"{existing} {addition}" if existing else addition


def _flag(record: RuleRecord, note: str) -> None:
    record.conflict_flag = True
    if note not in (record.conflict_note or ""):
        record.conflict_note = _append(record.conflict_note, note)


def apply_links(records: list[RuleRecord], cache: dict[str, Any]) -> None:
    by_key = {rule_key(r): r for r in records}
    for entry in cache.values():
        for link in entry["links"]:
            governing, yielding = by_key.get(link["governing"]), by_key.get(link["yielding"])
            if governing is None or yielding is None:
                continue
            if yielding.team_rule_id not in governing.overrides:
                governing.overrides.append(yielding.team_rule_id)
                governing.interaction = _append(
                    governing.interaction,
                    f"Supersedes {yielding.team_rule_id} ({yielding.title}): {link['explanation']}",
                )
            if governing.team_rule_id not in yielding.overrides:
                yielding.overrides.append(governing.team_rule_id)
                yielding.interaction = _append(
                    yielding.interaction,
                    f"Yields to {governing.team_rule_id} ({governing.title}): {link['explanation']}",
                )
            if link["uncertain"]:
                note = (
                    f"Uncertain whether {governing.team_rule_id} supersedes {yielding.team_rule_id}: "
                    f"{link['explanation']}"
                )
                _flag(governing, note)
                _flag(yielding, note)
        for conflict in entry["conflicts"]:
            involved = [by_key[k] for k in conflict["rules"] if k in by_key]
            ids = ", ".join(r.team_rule_id for r in involved)
            for record in involved:
                _flag(record, f"Conflict among {ids}: {conflict['note']}")
