from __future__ import annotations

PROMPT_VERSION = "v10"
NEW_DOCUMENT_PROMPT_VERSION = "v11-new-documents"

ORGANIZER_CONTEXT = """\
<organizer_context>
Context only. Never a source of rules, numbers, dates or quotes.

Brief, rule categories:
Category                                     What to capture
 Rent increase limits                         Cap formula, covered buildings, exemptions and local-versus-state precedence.
 Just-cause eviction                          Allowed causes, notice, relocation assistance and coverage.
 Security deposits                            Maximum, exceptions and effective date.
 Application and screening fees               Fee caps, allowed upfront charges, receipts and refunds.
 Screening restrictions                       Criminal-history and income-source limits and timing rules.
 Algorithmic rent-setting                     Covered software, prohibited conduct, penalties and effective date.

Starter pack README, section 9:
## 9. Known open questions in the law (bonus if your system surfaces them)

- **Berkeley's algorithmic ban** (ch. 13.63) has two published effective dates: March 1, 2026 in the ordinance text, January 2026 per an August 2026 law-firm alert.
- **New Jersey's FAIR Act** may preempt the Jersey City and Hoboken ordinances once it takes effect.
- **Los Angeles's new RSO formula** has two published effective dates: 2026-02-02 per LAHD, 2026-01-24 per a landlord association.
- **California's screening-fee cap** has no single official 2026 dollar figure.
</organizer_context>
"""

CITATION_STYLE = """\
Citation style (cite the law, never the web page):
"Cal. Civ. Code § 1947.12", "N.J.S.A. 46:8-21.2", "P.L.2025, c.405" (add the codified section as an alias),
"G.L. c. 186, § 15B", "G.L. c. 40P, § 4", "S.2983", "Initiative Petition 25-21", "S.F. Admin. Code ch. 37",
"L.A. Mun. Code § 151.06", "Berkeley Mun. Code ch. 13.63", "Jersey City Code § 218-12",
"Hoboken City Code ch. 158, Art. II", "Boston City Code § 10-11.7", "Cambridge Mun. Code ch. 8.71".
The primary citation is at section level (e.g. "Berkeley Mun. Code § 13.76.130",
"Cal. Code Regs. tit. 2, § 12264"). Always fill citation_aliases with the other forms: chapter-level
citation, bill and ordinance numbers (AB 1482, Ord. 25-057, NS-3090), session-law cites and popular
names (RSO, JCO, FAIR Act, Measure BB).
"""

EXTRACT_SYSTEM = """\
You read one source document about US residential rental housing law and return rule records,
no-rule findings and a one-paragraph doc_summary.

Categories (use exactly these):
- rent_increase_limits: caps, formulas, rent control, and state bars on local rent control.
- just_cause_eviction: allowed causes; eviction and termination notice requirements, including the content
  of a notice to quit and tenant-rights notices delivered with it; relocation assistance; reprisal
  protections tied to eviction.
- security_deposits: amount caps, return deadlines, interest, deductions, receipts.
- application_screening_fees: fee caps, allowed upfront charges, receipts and refunds, broker-fee allocation.
- screening_restrictions: limits on what a landlord may consider (criminal history, source of income,
  credit, eviction records) and timing rules.
- algorithmic_rent_setting: bans or limits on algorithmic or coordinated rent-setting software, including
  pending bills.

Granularity:
- One record per law per category: a statute section family, an ordinance or code chapter, a bill, or a
  ballot measure. Usually 0 to 3 records per category. Fold definitions, notice periods, penalties, return
  deadlines, interest and annual rate bulletins into the law's main record.
- A law that spans two categories yields one record per category (G.L. c. 186, § 15B gives a
  security_deposits record AND an application_screening_fees record).
- A relocation section that is its own code section is its own record.
- A law whose only effect is to exempt buildings from another rule is not a record: express it as coverage
  of the limited rule.
- A document that describes several jurisdictions yields one record per jurisdiction's law, with the law's
  own jurisdiction (a Berkeley page describing California deposit law gives jurisdiction "CA").
- Jurisdiction format: two-letter state ("CA", "NJ", "MA") or "City, ST".
- Failed measures get a record with status failed (a ballot question struck from the ballot, a home-rule
  petition sent to a study order). Motions, hearings and studies are no_rule_findings, not rules.
- Rules triggered only by an event (demolition relocation, Ellis Act withdrawal, condo conversion,
  temporary displacement): set event_only true.
- A state statute limited by its text to one city: applies_only_in = that city ("Boston, MA").
- When the document states that a jurisdiction has no rule in a category, or that a state bars a local
  rule, record a no_rule_finding with the verbatim quote.

Coverage (who and what is covered, never conduct):
- min_units, max_units; construction_cutoff {basis, covered_if, date}; new_construction_exemption
  {years, basis, requires_owner_filing}; owner_occupied_exemption_max_units; requires_unknown_facts only when
  the whole rule is limited to buildings not identifiable from assessor data; unverifiable_exemptions
  (exemptions an address lookup cannot check, e.g. subsidized units, units with a recorded deed
  restriction); yields_to_local_rule; supersedes_state_rule; may_preempt_local_rules;
  landlord_size_condition. Also fill summary, construction_date_basis, built_on_or_before, built_after,
  min_building_age_years, owner_conditions, other_conditions as net coverage (an exemption for units built
  after 1978 means built_on_or_before 1978).
- Leave a field null when the text does not state it.

Dates:
- effective_date: when the headline requirement first took effect. enacted_date, sunset_date,
  effective_date_note for anything ambiguous.
- If the text states the effective date as a formula ("first day of the fourth month next following
  enactment", "the twelfth month after approval", "90 days after"), fill effective_date_formula with the
  verbatim wording and anchor date, and leave effective_date null: the date is computed in code.
- An adopted ordinance replaces its proposed version: when both are present, describe the adopted one.
- Judge status as of the query date (code recomputes it from effective_date): in_force, not_yet_effective (enacted, takes effect later), pending
  (not passed), failed (defeated, vetoed, struck, sent to study).

key_value is mandatory whenever the text states an amount, rate, deadline or penalty (e.g. "1 month's
rent max; return within 30 days; 3x damages"). Null only when the text states none.

Evidence:
- quoted_span is copied character for character from the document: one contiguous passage that states
  the requirement, no ellipses, no paraphrase, no added punctuation.
- Use only what the document says. Never add a rule, number, date or citation from background knowledge.
  Secondary sources (FAQ, news, law-firm alert): extract what they describe, cite the law they name,
  lower confidence.
- conflict_flag and conflict_note ONLY for an open question: official sources that disagree on a date or
  value, possible preemption between levels, or an unresolved organizer open question. A discrepancy the
  documents resolve (e.g. a secondary source repeats an outdated date) goes to source_notes, not
  conflict_note. Other caveats go to review_note.
- candidate_id: "c1", "c2", ... in document order.

""" + CITATION_STYLE + "\n" + ORGANIZER_CONTEXT

_OLD_KEY_VALUE_INSTRUCTION = """key_value is mandatory whenever the text states an amount, rate, deadline or penalty (e.g. "1 month's
rent max; return within 30 days; 3x damages"). Null only when the text states none."""
_NEW_KEY_VALUE_INSTRUCTION = """key_value must begin with a compact summary of the law's main obligation or prohibition. Include a
numeric cap, rate or deadline when it is itself the obligation. Put fines, damages, remedies and procedural notice periods after the
substantive duty, never in place of it. Null only when the text states no substantive duty or useful key value."""
assert _OLD_KEY_VALUE_INSTRUCTION in EXTRACT_SYSTEM
NEW_DOCUMENT_EXTRACT_SYSTEM = EXTRACT_SYSTEM.replace(
    _OLD_KEY_VALUE_INSTRUCTION, _NEW_KEY_VALUE_INSTRUCTION
)

EXTRACT_HUMAN = """\
Query date: {query_date}
Document ID: {doc_id}
Jurisdiction(s) per manifest: {jurisdictions}
Source type: {source_type}
Source URL: {url}
<document>
{text}
</document>"""

RECOPY_SYSTEM = """\
Some quotes attributed to this document could not be found in it. For each candidate, copy from the
document, character for character, the shortest contiguous passage that states the same requirement.
Return null when the document has no such passage. Never paraphrase."""

RECOPY_HUMAN = """\
<document>
{text}
</document>
<failed_quotes>
{failed}
</failed_quotes>"""

CONSOLIDATE_SYSTEM = """\
You consolidate candidate rule records for one jurisdiction into final records, one per law per category.

Rules:
- Merge candidates that describe the same law (same statute section family, ordinance, bill or measure).
  Never merge a pending or failed measure into an enacted law.
- Fix category, jurisdiction, status and coverage against the full documents provided.
- Drop non-rules (motions, studies, restatements, out-of-scope topics) with a reason.
- Every candidate id must appear in exactly one rule's from_candidates or in dropped_candidates.
- Prefer quotes from official documents; keep secondary support in also_supported_by. Every quoted_span
  must be copied verbatim from the document named by source_doc_id.
- Complementary local coverage stays complementary (e.g. a just-cause ordinance covering units built
  after a rent ordinance's cutoff gets the complementary construction_cutoff).
- conflict_flag and conflict_note ONLY for an open question: official sources that disagree on a date or
  value, possible preemption between levels, or an unresolved organizer open question. A discrepancy the
  documents resolve (e.g. a secondary source repeats an outdated date) goes to source_notes, not
  conflict_note. Other caveats go to review_note.
- Never add a rule from background knowledge. If you know of a law the documents name but whose text is
  not captured, list it under known_gaps instead of creating a rule.
- Use the other level's rules (state for a city, cities for a state) only as context for precedence.
- Scope: only the jurisdiction named below. A candidate about any other place (another state, county or
  city) is dropped with reason "out of scope".
- A proposed or draft version of an ordinance and its adopted version are ONE record (the adopted one,
  status from its dates); keep a separate pending record only when no adopted version exists.
- A rent rule triggered only by an event (condominium or cooperative conversion, demolition, Ellis Act
  withdrawal) is event_only=true and belongs to just_cause_eviction, not rent_increase_limits.
- Open questions: when a record concerns one of the organizer's section 9 open questions and the documents
  show the disagreement (two published effective dates, possible preemption, no single official figure),
  set conflict_flag true and name the open question in conflict_note.
- A state law that does not itself cap rents is not a state rent_increase_limits record: a statute that only
  exempts buildings from local rent control (e.g. a 30-year exemption for new construction) becomes
  coverage of the municipal rent control records (new_construction_exemption) and is dropped as a record
  with reason "exemption folded into municipal coverage"; notice, unconscionability or mid-lease rules
  belong to their own category (just_cause_eviction) or are dropped as out of scope.

""" + CITATION_STYLE + "\n" + ORGANIZER_CONTEXT

CONSOLIDATE_HUMAN = """\
Query date: {query_date}
Jurisdiction: {jurisdiction}

<candidates>
{candidates}
</candidates>

<documents>
{documents}
</documents>

<link_only_sources>
{links}
</link_only_sources>

<other_level_rules>
{context_rules}
</other_level_rules>"""

PROBE_SYSTEM = """\
For one jurisdiction and each listed category that has no rule, decide from the documents only:
- no_rule: a document supports that the jurisdiction has no such rule (or that it is barred). Give the
  doc_id, a verbatim quoted_span and the basis_citation when the document names the law.
- undetermined: the documents do not settle it.
Retrieved passages (BM25 over the whole corpus) are included: check them before deciding.
Never answer from background knowledge."""

PROBE_HUMAN = """\
Jurisdiction: {jurisdiction}
Empty categories: {categories}
<documents>
{documents}
</documents>"""

COVERAGE_SYSTEM = """\
Audit the coverage object of one rule against the documents of its jurisdiction. Return the corrected
coverage and, for every non-null and non-empty coverage value, an evidence item {field, doc_id,
quoted_span} where quoted_span is copied verbatim from that document. A value you cannot support with a
verbatim passage must be null (or omitted from lists). Coverage describes buildings, units and owners,
never landlord conduct.
requires_unknown_facts is true ONLY when the rule as a whole applies to a class of buildings that assessor
data cannot identify (e.g. only subsidized units, only units under a specific regulatory agreement). A rule
that covers ordinary rental buildings and merely has some exemptions an address lookup cannot check is NOT
requires_unknown_facts: list those exemptions in unverifiable_exemptions instead. Express construction-date
limits with construction_cutoff, not with requires_unknown_facts."""

COVERAGE_HUMAN = """\
<rule>
{rule}
</rule>
<documents>
{documents}
</documents>"""

DATE_SYSTEM = """\
Audit the dates of one rule from the documents only. Return:
- requirement_is_new: true if the headline requirement did not exist in any earlier form.
- in_force_since: the date the requirement (any version) first applied, with verbatim evidence.
- current_version_effective: the date the current version took effect.
- prior_version_note: what the earlier version required, if the documents say.
- effective_date_formula when a document states the date as a formula (the code computes it).
Leave unknown values null."""

DATE_HUMAN = COVERAGE_HUMAN

QA_SYSTEM = """\
Legal QA of one rule record. You may change only these fields: category, status, effective_date,
in_force_since, current_version_effective, coverage.construction_cutoff (direction and date), applies_only_in,
event_only, conflict_flag, conflict_note, citation (format only). Propose a change only when the documents
show the record is wrong; give the new value as JSON in after_json and a one-sentence reason. Return an
empty list when the record is right.

""" + CITATION_STYLE

QA_HUMAN = COVERAGE_HUMAN

RESOURCE_SYSTEM = """\
The rule below is supported by a quote from a secondary source. If one of the official documents states
the same requirement, return that document's id and a verbatim quoted_span from it. Otherwise return null."""

RESOURCE_HUMAN = COVERAGE_HUMAN

CELL_SYSTEM = """\
You read retrieved passages for ONE jurisdiction and ONE category and return the rules of THIS jurisdiction
at THIS level only (a state's statutes for a state; a city's own ordinances for a city; never the other
level's law). One record per legal instrument (statute section family, ordinance or chapter, bill, ballot
measure). Each record names the passage_id its quoted_span is copied from, character for character.
cell_status: rules_found; no_rule_stated (a passage states this jurisdiction has no such rule, or that it is
barred: give no_rule_quote verbatim, its no_rule_passage_id and basis_citation); silent (the passages do not
say). Never use background knowledge. Status, coverage, dates, key_value and citation follow the same rules
as per-document extraction:
""" + EXTRACT_SYSTEM.split("Categories (use exactly these):")[1]

CELL_HUMAN = """\
Query date: 2026-10-01
Jurisdiction: {jurisdiction}
Category: {category}
<passages>
{passages}
</passages>"""

FIELD_CHECK_SYSTEM = """\
Verify one rule record against its source document. For each of requirement, key_value, effective_date,
status, coverage and citation return a verdict: supported, partly_supported, not_supported, or
not_applicable (the field is empty and the document states nothing for it). Every supported or
partly_supported verdict carries a quoted_span copied verbatim from the document. Judge only from the
document."""

FIELD_CHECK_HUMAN = """\
<rule>
{rule}
</rule>
<document id="{doc_id}">
{text}
</document>"""

PLAIN_SYSTEM = """\
Write one plain-language sentence in English (en) and one in Spanish (es) telling a renter what this rule
does. Use only facts in the record; every number you write must appear in the record. No advice."""
