from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Level = Literal["state", "city"]

Category = Literal[
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
]

Status = Literal["in_force", "not_yet_effective", "pending", "failed"]

DateBasis = Literal["year_built", "certificate_of_occupancy", "first_occupancy"]

DATE_PATTERN = r"^\d{4}(-\d{2}(-\d{2})?)?$"
_DATE_PREFIX = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?")


def _coerce_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _DATE_PREFIX.match(value.strip())
    return match.group(0) if match else None


class Coverage(BaseModel):

    summary: str | None = Field(
        description="Plain-language description of which units and owners are covered, net of exemptions."
    )
    construction_date_basis: DateBasis | None = Field(
        description=(
            "What the construction cutoff is measured by, as the text states it: 'year_built', "
            "'certificate_of_occupancy' or 'first_occupancy'. Null if there is no construction cutoff."
        )
    )
    built_on_or_before: str | None = Field(
        description=(
            "Covered only if built (per construction_date_basis) on or before this date, as YYYY, "
            "YYYY-MM or YYYY-MM-DD. If the text says strictly 'before' a date, use the day before."
        )
    )
    built_after: str | None = Field(
        description="Covered only if built (per construction_date_basis) after this date, as YYYY, YYYY-MM or YYYY-MM-DD."
    )
    min_building_age_years: int | None = Field(
        description=(
            "Rolling cutoff: covered only if the building is at least this many years old, e.g. 15 when "
            "units with a certificate of occupancy issued within the previous 15 years are exempt."
        )
    )
    min_units: int | None = Field(
        description="Covered only if the property has at least this many units, e.g. 3 when properties with 2 or fewer units are exempt."
    )
    max_units: int | None = Field(description="Covered only if the property has at most this many units.")
    owner_conditions: str | None = Field(
        description=(
            "Conditions on the owner, such as owner type, owner occupancy or portfolio size, e.g. 'exempt if "
            "owned by a natural person who gave notice'. Null if coverage doesn't depend on the owner."
        )
    )
    other_conditions: str | None = Field(
        description="Any other coverage condition (unit type, subsidies, tenancy length, ...). Null if none."
    )

    @field_validator("built_on_or_before", "built_after", mode="before")
    @classmethod
    def _dates(cls, value: Any) -> str | None:
        return _coerce_date(value)

    def is_empty(self) -> bool:
        return all(v is None for v in self.model_dump().values())


class RuleRecord(BaseModel):

    model_config = ConfigDict(extra="forbid")

    team_rule_id: str = Field(description="Your own unique id, e.g. 'r-0001'.")
    jurisdiction: str = Field(
        description="State code ('CA','NJ','MA') or 'City, ST' (e.g. 'San Francisco, CA')."
    )
    level: Level
    category: Category
    status: Status = Field(
        description=(
            "As of the query date (default 2026-10-01). Enacted laws with a future "
            "effective date are 'not_yet_effective'."
        )
    )
    title: str
    requirement: str = Field(description="One or two plain-language sentences.")
    key_value: str | None = Field(
        default=None,
        description="The headline number or formula, e.g. '1.5 months rent', 'lesser of CPI or 4%'.",
    )
    coverage_conditions: str | dict[str, Any] | None = Field(
        default=None,
        description=(
            "Who/what is covered: year built or certificate-of-occupancy cutoffs, "
            "unit counts, owner type."
        ),
    )
    exemptions: str | None = None
    overrides: list[str] = Field(
        default_factory=list,
        description="team_rule_ids this rule supersedes or yields to, with direction in 'interaction'.",
    )
    interaction: str | None = None
    effective_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    citation: str = Field(description="Official cite, e.g. 'Cal. Civ. Code § 1947.12'.")
    source_doc_id: str | None = Field(default=None, description="doc_id from corpus_manifest.csv.")
    source_url: str
    quoted_span: str = Field(
        min_length=20,
        description="Exact text copied from the source document that supports the rule.",
    )
    confidence: float | None = Field(default=None, ge=0, le=1)
    conflict_flag: bool = False
    conflict_note: str | None = None


class ExtractedRule(BaseModel):

    jurisdiction: str = Field(
        description=(
            "Jurisdiction that enacted the rule. Use the two-letter state code for state "
            "law ('CA', 'NJ', 'MA') or 'City, ST' for city law (e.g. 'San Francisco, CA')."
        )
    )
    level: Level = Field(description="'state' for state law, 'city' for municipal law.")
    category: Category = Field(description="The single best-fitting rule category.")
    status: Status = Field(
        description=(
            "Status as of the query date: 'in_force' if enacted and effective; "
            "'not_yet_effective' if enacted but the effective date is after the query date; "
            "'pending' for a bill or proposal not yet enacted; 'failed' for a bill, "
            "ordinance or ballot measure that was defeated, vetoed, withdrawn or struck."
        )
    )
    title: str = Field(description="Short name of the rule, e.g. 'Statewide rent cap (AB 1482)'.")
    requirement: str = Field(
        description="One or two plain-language sentences stating what the rule requires or prohibits."
    )
    key_value: str | None = Field(
        description=(
            "The headline number or formula, e.g. '1 month's rent', 'lesser of 5% + CPI or 10%'. "
            "Null if the rule has no headline number."
        )
    )
    coverage_conditions: Coverage = Field(
        description=(
            "Who/what is covered, as concretely as the text allows. Fill the structured fields "
            "whenever the text gives a construction cutoff, unit-count threshold or owner condition."
        )
    )
    exemptions: str | None = Field(description="Exempted units, buildings or owners. Null if none stated.")
    interaction: str | None = Field(
        description=(
            "How this rule interacts with rules at other levels, e.g. 'Yields to stricter "
            "local rent control' or 'May preempt local algorithmic-pricing ordinances'. Null if none stated."
        )
    )
    effective_date: str | None = Field(
        description="Effective date as YYYY, YYYY-MM or YYYY-MM-DD. Null if not stated in the text."
    )
    citation: str = Field(
        description=(
            "Official citation as written in or derivable from the text, e.g. "
            "'Cal. Civ. Code § 1947.12', 'BMC 13.63.030', 'N.J.S.A. 46:8-21.2', 'S.2983'. "
            "Never invent a section number."
        )
    )
    quoted_span: str = Field(
        description=(
            "One contiguous passage copied verbatim, character for character, from the "
            "document that supports the rule. At least 20 characters, ideally one to three "
            "sentences. No ellipses, no paraphrase, no added or removed words."
        )
    )
    confidence: float | None = Field(
        description="Your confidence from 0 to 1 that this record is accurate and correctly classified."
    )
    conflict_flag: bool = Field(
        description=(
            "True if the text signals a conflict or open question needing human review, e.g. "
            "two different effective dates, possible preemption, or a pending legal challenge."
        )
    )
    conflict_note: str | None = Field(description="What the conflict is, if conflict_flag is true.")

    @field_validator("effective_date", mode="before")
    @classmethod
    def _date(cls, value: Any) -> str | None:
        return _coerce_date(value)

    @field_validator("coverage_conditions", mode="before")
    @classmethod
    def _coverage_from_text(cls, value: Any) -> Any:
        if value is None or isinstance(value, str):
            return {name: None for name in Coverage.model_fields} | {"summary": value or None}
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return None


class ExtractionResult(BaseModel):

    rules: list[ExtractedRule] = Field(
        description="All distinct rules in the text that fall into one of the categories. Empty if none."
    )
