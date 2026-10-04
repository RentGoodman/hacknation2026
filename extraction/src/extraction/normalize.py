from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bM\.?\s*G\.?\s*L\.?\s*(?:c\.|ch\.|chapter)\s*", re.I), "G.L. c. "),
    (re.compile(r"\bMass\.?\s+Gen\.?\s+Laws\s+(?:c\.|ch\.|chapter)\s*", re.I), "G.L. c. "),
    (re.compile(r"\bG\.L\.\s*c\.\s*"), "G.L. c. "),
    (re.compile(r"\bN\.?\s*J\.?\s*S\.?\s*A\.?\s*", re.I), "N.J.S.A. "),
    (re.compile(r"\bP\.\s*L\.\s*(\d{4})\s*,\s*c\.\s*", re.I), r"P.L.\1, c."),
    (re.compile(r"\bCal(?:ifornia)?\.?\s+Civ(?:il)?\.?\s+Code\s*", re.I), "Cal. Civ. Code "),
    (re.compile(r"\bCal(?:ifornia)?\.?\s+Gov(?:ernment|\'t)?\.?\s+Code\s*", re.I), "Cal. Gov. Code "),
    (re.compile(r"\bCal(?:ifornia)?\.?\s+Bus(?:iness)?\.?\s*(?:&|and)\s*Prof(?:essions)?\.?\s+Code\s*", re.I),
     "Cal. Bus. & Prof. Code "),
    (re.compile(r"\bLAMC\b\s*§?\s*", re.I), "L.A. Mun. Code § "),
    (re.compile(r"\bLos Angeles Municipal Code\s*§?\s*", re.I), "L.A. Mun. Code § "),
    (re.compile(r"\bBMC\b\s*§?\s*"), "Berkeley Mun. Code § "),
    (re.compile(r"\bBerkeley Municipal Code\s*§?\s*", re.I), "Berkeley Mun. Code § "),
    (re.compile(r"\bCambridge Municipal Code\s*", re.I), "Cambridge Mun. Code "),
    (re.compile(r"\bSan Diego Municipal Code\s*§?\s*", re.I), "SDMC § "),
    (re.compile(r"\bS\.?\s*F\.?\s+Rent Ordinance\s*§?\s*", re.I), "S.F. Admin. Code § "),
    (re.compile(r"\bSan Francisco Rent Ordinance\s*§?\s*", re.I), "S.F. Admin. Code § "),
    (re.compile(r"\bS\.?\s*F\.?\s+Admin(?:istrative)?\.?\s+Code\s*", re.I), "S.F. Admin. Code "),
    (re.compile(r"\bJersey City (?:Municipal )?Code\s*", re.I), "Jersey City Code "),
    (re.compile(r"\bHoboken (?:City |Municipal )?Code\s*", re.I), "Hoboken City Code "),
    (re.compile(r"\bBoston (?:City |Municipal )?Code\s*", re.I), "Boston City Code "),
    (re.compile(r"\bAssembly Bill\s+", re.I), "AB "),
    (re.compile(r"\bSenate Bill\s+", re.I), "SB "),
    (re.compile(r"\bchapter\s+(\d)", re.I), r"ch. \1"),
]

_SECTION_FIX = [
    (re.compile(r"§\s*§\s*"), "§§ "),
    (re.compile(r"§(?=\S)"), "§ "),
    (re.compile(r"(\d)\s*:\s*(\d)"), r"\1:\2"),
    (re.compile(r"c\.\s*(\d)"), r"c. \1"),
    (re.compile(r"P\.L\.(\d{4}), c\. (\d)"), r"P.L.\1, c.\2"),
    (re.compile(r"(c\. \w+),?\s+§"), r"\1, §"),
    (re.compile(r"\s+"), " "),
]

_CODE_SECT = re.compile(r"(Code|Mun\. Code) § (ch\.)", re.I)


def normalize_citation(text: str | None) -> str | None:
    if text is None:
        return None
    out = text.strip()
    for pat, rep in _RULES:
        out = pat.sub(rep, out)
    for pat, rep in _SECTION_FIX:
        out = pat.sub(rep, out)
    out = _CODE_SECT.sub(r"\1 \2", out)
    return out.strip().rstrip(";,")


_KEY_SECTION = re.compile(r"(§+\s*[\w.:-]+?)(?=\(|,|;|\s|$)")


def law_key(citation: str | None) -> str:
    if not citation:
        return ""
    first = normalize_citation(citation).split(";")[0]
    first = re.sub(r"\(.*?\)", "", first)
    first = re.sub(r"\s+(et seq\.|to\s+-?[\w.]+).*$", "", first)
    m = re.search(r"§+\s*[\w.:-]+", first)
    if m:
        first = first[: m.end()]
    first = first.rstrip(" ,-.")
    first = re.sub(r"(\d+(?:\.\d+)?)(?:\.[A-Z](?:\.\d+)*)$", r"\1", first.strip())
    return re.sub(r"\s+", " ", first).strip().lower()
