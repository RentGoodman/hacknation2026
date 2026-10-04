# Self-check

17/17 checks pass.

| Check | Result | Detail |
|---|---|---|
| strict full-record schema validity | pass | 68 complete records valid; official schema permits 21 extension fields |
| 100% verbatim spans | pass | 68/68 exact |
| lookups template contract | pass | 500/500 addresses; malformed entries: [] |
| jurisdiction boundaries | pass | 0 leaks [] |
| SF example: pre-1979 SF rent ordinance applies, state cap superseded | pass | A0016 (1926): r-0039 CA superseded, r-0179 San Francisco, CA applies |
| changes template contract | pass | T1-T5 contain affected ids, conflict ids and notes |
| change test T1 | pass | Mapping: CA-ALG-01 maps to r-0034. Affected = addresses whose mapped rule goes from not_yet_effective on 2025-12-31 to a |
| change test T2 | pass | Mapping: HOB-ALG-01 maps to r-0161; JC-ALG-01 maps to r-0146. Affected = addresses where a mapped local rule's result is |
| change test T3 | pass | Mapping: NJ-ALG-01 maps to r-0173. Compared results on 2026-10-01 and 2027-07-02; affected = not_yet_effective -> applie |
| change test T4 | pass | Mapping: MA-ALG-P1 maps to r-0076, r-0077; MA-ALG-P2 maps to r-0076, r-0077. Simulated enactment (status in force, effec |
| change test T5 | pass | Mapping: MA-RENT-P1 maps to r-0148. r-0148 status failed; a failed rule is omitted from every lookup. Checked only petit |
| no-rule findings are evidence-backed | pass | 2 verified negative findings |
| no in_force rule in a no-rule cell | pass | [] |
| open question surfaced: Berkeley algorithmic ban: two effective dates | pass | r-0001 |
| open question surfaced: NJ FAIR Act may preempt Jersey City / Hoboken | pass | r-0146, r-0161 |
| open question surfaced: LA RSO formula: two effective dates | pass | r-0166 |
| open question surfaced: CA screening-fee cap: no single official 2026 figure | pass | r-0007 |
