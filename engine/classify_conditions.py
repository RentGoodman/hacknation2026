import hashlib
import json
import re
from pathlib import Path

MODEL = "sonnet"
CACHE = Path(__file__).resolve().parent / "cache" / "conditions.json"
FIELDS = ("owner_conditions", "other_conditions", "exemptions")
EFFECTS = {"excludes_coverage", "modifies_terms", "informational"}

PROMPT_VERSION = "v5"
PROMPT = """You classify conditions attached to a US residential landlord-tenant rule.
Rule: {title}
Requirement: {requirement}

The only question: does this condition decide whether the rule COVERS a given address? The data has, per building:
state, city, year built, number of units, property type. It has no owner identity, no tenancy dates, no tenant facts.

For each condition return "effect":
- "excludes_coverage": ONLY a fact about the building, the unit, the owner or the tenancy that removes the address
  from the rule's scope (e.g. owner-occupied buildings, single-family homes, small landlords, government-owned or
  subsidized or affordable housing only, newly constructed buildings, units under another regime).
- "informational": anything describing the prohibited conduct, the elements of a violation, or enforcement: use or
  sharing of competitor data, use of an algorithm by two or more persons, coercion, a discriminatory act, a notice
  or filing duty, penalties, who may sue. These never decide coverage. Also anything with no effect on scope.
- "modifies_terms": the rule still covers the address; the condition changes an amount, deadline or procedure,
  which tenancies or events trigger a duty (tenancy start dates, "when the landlord deducts", service members),
  or offers an alternative amount (e.g. "small landlords may charge two months").
units_max: ONLY if the condition text itself states that the excluded (or covered) buildings have at most N units
(single-family = 1, duplex = 2, "two or fewer units" = 2, "no more than four units" = 4); else null.
units_clause: the exact words of the condition that state that unit limit (verbatim), else null.
can_exclude_apartment_building: for "excludes_coverage" only, true if this exclusion could remove an ordinary
residential multifamily apartment building rented as primary residences (e.g. owner-occupied, small landlord,
subsidized, new construction, rent-controlled elsewhere); false if it only removes other kinds of property (medical
or long-term care, detention, hotels, dormitories, nonresidential, single-family homes); null otherwise.
situation: for "excludes_coverage" only, one of:
  "unusual" - an exemption for an unusual situation of a unit or tenancy (seasonal or vacation rental, a single
    tenant or roommate in the owner's home, trust for a family member with a disability, detention, shared kitchen
    or bath with the owner, transient occupancy);
  "restricted_coverage" - the rule only covers a narrow positive category (affordable or subsidized units only,
    IDP/DND units only, units under a specific program only);
  "references_coverage" - coverage is defined by another ordinance's coverage (e.g. "units subject to the RSO",
    "covered by the JCO"); then give "references": the referenced ordinance name or acronym as written;
  "ordinary" - any other exclusion; null when not excludes_coverage.
Give a short label (2-4 words).

Conditions:
{items}

Answer with JSON only: {{"conditions": [{{"field": "...", "effect": "...", "units_max": null, "units_clause": null, "can_exclude_apartment_building": null, "situation": null, "references": null, "label": "..."}}]}}"""

def _texts(rule):
    cov = rule.get("coverage_conditions") if isinstance(rule.get("coverage_conditions"), dict) else {}
    out = []
    for f in FIELDS:
        t = rule.get(f) if f == "exemptions" else cov.get(f)
        if isinstance(t, str) and t.strip():
            out.append((f, t.strip()))
    return out


def _key(rule, texts, version=None):
    h = hashlib.sha256(json.dumps(texts, sort_keys=True).encode()).hexdigest()[:16]
    return f"{rule['team_rule_id']}:{version or PROMPT_VERSION}:{h}"


WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"


def _n(w):
    w = w.lower()
    return WORDS.get(w) or (int(w) if w.isdigit() else None)


EXCLUSION = re.compile(r"\b(does not apply|do not apply|shall not apply|not apply to|is exempt|are exempt|exempts?|"
                       r"exempted|excluded|excludes|not covered|only applies|applies only|only if|only when|unless)\b", re.I)
AMOUNT = re.compile(r"\b(may charge|charge up to|up to|months?'? rent|cap|amount|fee|deduct\w*|advance payment|"
                    r"interest|deadline|days?|photograph\w*|itemi[sz]ed|walk-through|notice)\b", re.I)
TRANSITIONAL = re.compile(r"\b(before|after|on or after|prior to|beginning|starting|from)\s+(?:\w+\s+)?"
                          r"(january|february|march|april|may|june|july|august|september|october|november|december|"
                          r"\d{4})", re.I)
SUBPROVISION = re.compile(r"^\s*(?:subd\.|subdivision|paragraph|clause|section)\s*\([a-z0-9]+\)\s+"
                          r"(?:applies|apply)\s+only\b", re.I)


def heuristic(field, text):
    units_max = None
    owner = re.search(r"\b(landlords?|owners?|natural persons?|family trust|llc)\b", text, re.I)
    if SUBPROVISION.search(text):
        effect = "modifies_terms"
    elif TRANSITIONAL.search(text):
        effect = "modifies_terms"
    elif AMOUNT.search(text) and not EXCLUSION.search(text):
        effect = "modifies_terms"
    elif EXCLUSION.search(text):
        effect = "excludes_coverage"
    elif AMOUNT.search(text):
        effect = "modifies_terms"
    else:
        effect = "informational"
    label = "small-landlord exception" if owner else ("exemption" if effect == "excludes_coverage" else "condition")
    return {"field": field, "effect": effect, "units_max": units_max, "units_clause": None, "label": label}


def heuristic_v1(field, text):
    t = text.lower()
    units_max = None
    owner = re.search(r"\b(landlord|owner|natural person|family trust|llc)\b", t)
    if re.search(r"\b(exempt|does not apply|not apply|only (applies|if|when)|excluded|unless|applies only)\b", t) \
            or (field == "exemptions") or (owner and units_max is not None):
        effect = "excludes_coverage"
    elif re.search(r"\b(deduct|amount|month|days?|deadline|photograph|return|interest|fee|percent|%)\b", t):
        effect = "modifies_terms"
    else:
        effect = "informational"
    return {"field": field, "effect": effect, "units_max": units_max, "label": "condition"}


STOP_MARKERS = ("llm unavailable", "rate", "quota", "429", "credit", "529", "usage limit", "limit reached",
                "overloaded")


def _ask(prompt):
    from llm.backend import backend_label, complete
    return complete(prompt, model=MODEL), backend_label(MODEL)


def _forget(prompt):
    from llm.backend import forget
    forget(prompt, model=MODEL)


def _claude(rule, texts):
    items = "\n".join(f"- field={f}: {t}" for f, t in texts)
    prompt = PROMPT.format(title=rule.get("title", ""), requirement=rule.get("requirement", ""), items=items)
    raw, label = _ask(prompt)
    try:
        if "{" not in raw:
            raise ValueError(f"no JSON in model reply: {raw[:120]!r}")
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        data["conditions"]
    except Exception:
        _forget(prompt)
        raise
    out = []
    for (f, t), c in zip(texts, data["conditions"]):
        eff = c.get("effect") if c.get("effect") in EFFECTS else "informational"
        um, clause = c.get("units_max"), c.get("units_clause")
        ok = isinstance(um, int) and isinstance(clause, str) and clause.strip() and \
            " ".join(clause.lower().split()) in " ".join(t.lower().split())
        cx = c.get("can_exclude_apartment_building")
        sit = c.get("situation") if c.get("situation") in ("unusual", "restricted_coverage", "references_coverage",
                                                            "ordinary") else None
        ref = c.get("references") if sit == "references_coverage" and isinstance(c.get("references"), str) else None
        out.append({"field": f, "effect": eff, "units_max": um if ok else None,
                    "units_clause": clause.strip() if ok else None,
                    "can_exclude_apartment_building": cx if isinstance(cx, bool) else None,
                    "situation": sit if eff == "excludes_coverage" else None, "references": ref,
                    "label": c.get("label") or "condition"})
    return out, label


def classify(rules, use_api=True, fallback=None, use_cache=True):
    stored = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    cache = stored if use_cache else {}
    log, api_error, dirty = [], None, False
    skipped = []
    for r in rules:
        texts = _texts(r)
        if not texts:
            r["_conditions"] = None
            continue
        key = _key(r, texts)
        entry = cache.get(key)
        if entry is None and use_api and api_error is None:
            for attempt in range(3):
                try:
                    conds, label = _claude(r, texts)
                    entry = {"classifier": label, "conditions": conds}
                    cache[key], dirty = entry, True
                    break
                except Exception as e:
                    msg = f"{type(e).__name__}: {str(e)[:160]}"
                    stop = any(w in msg.lower() for w in STOP_MARKERS)
                    if attempt < 2 and not stop:
                        import time
                        time.sleep(5)
                        continue
                    if stop:
                        api_error = msg
                    else:
                        skipped.append(f"{r['team_rule_id']}: {msg}")
                    break
        if entry is None:
            fb = fallback or heuristic
            entry = {"classifier": "heuristic (Claude call unavailable)",
                     "conditions": [fb(f, t) for f, t in texts]}
        conds = [dict(c, text=t) for c, (_, t) in zip(entry["conditions"], texts)]
        r["_conditions"] = conds
        log.append({"team_rule_id": r["team_rule_id"], "classifier": entry["classifier"],
                    "conditions": [{k: c.get(k) for k in ("field", "effect", "units_max", "units_clause", "can_exclude_apartment_building", "situation",
                                       "references", "label")} for c in conds]})
    if dirty:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    if skipped and not api_error:
        api_error = f"{len(skipped)} rule(s) fell back to the heuristic after a failed call: " + "; ".join(skipped[:5])
    return log, api_error



PROMPT_VERSION_V6 = "v6"
V6_CLASSIFIER = "claude (Claude Code session, no API key)"
NATURES = ("positive_limit", "exemption", "informational", "modifies_terms")
SITUATIONS = ("unusual", "ordinary", "restricted_coverage", "references_coverage")
PROPERTY_TYPES = ("single_family", "condo", "townhome", "mobile_home", "duplex", "triplex", "room_in_owner_home",
                  "hotel", "care_facility", "dormitory", "other")
PROMPT_V6 = """You classify conditions attached to a US residential landlord-tenant rule.
Rule: {title}
Requirement: {requirement}

The data has, per building: state, city, year built, number of units (sometimes only an interval), property type
(multifamily, mixed use...). It has no owner identity, no owner occupancy, no tenancy dates, no tenant facts.

For each condition return "nature":
- "positive_limit": the rule covers ONLY a narrow category (subsidized or affordable units only, IDP/DND units only,
  units in a program only, units subject to another ordinance only). Unverified, the rule's coverage is unknown.
- "exemption": the rule covers everything EXCEPT the listed cases ("exempt", "does not apply to", "excludes",
  "covered by another ordinance instead"). Most "exempt X" clauses are exemptions, even long lists.
- "modifies_terms": the rule still covers the address; an amount, deadline, procedure or trigger changes.
- "informational": conduct, elements of a violation, definitions of a product, enforcement; no effect on scope.
owner_linked: true if the exemption (or positive limit) depends on the owner (owner-occupied, natural person, small landlord, owner not
  a REIT or corporation, owner shares a kitchen or bath); else false.
owner_exemption_max_units: an integer ONLY if the condition text states word for word the building size of the
  owner-linked exemption ("1-3 unit property" = 3, "not more than four dwelling units" = 4, "two-family" = 2,
  "two- or three-family" = 3); else null. owner_units_clause: the exact words stating it (verbatim), else null.
property_types_targeted: the property types the exemption targets, from this closed list only: single_family,
  condo, townhome, mobile_home, duplex, triplex, room_in_owner_home, hotel, care_facility, dormitory, other.
affordable_targeted: true if the exemption removes deed-restricted, subsidized or affordable housing; else false.
situation: for positive_limit and exemption only, one of:
  "unusual" - a rare use of a unit or tenancy (seasonal or vacation rental, hotel or transient occupancy, care
    facility, detention, dormitory, shared kitchen or bath with the owner, transitional occupancy, a single roommate
    in the owner's home, trust for a family member with a disability, approval by application);
  "restricted_coverage" - a positive_limit that is not a reference to another ordinance;
  "references_coverage" - coverage defined by another ordinance's coverage ("units subject to the RSO", "covered by
    that ordinance instead"); then give "references": the referenced ordinance name or acronym as written;
  "ordinary" - any other exemption. null for modifies_terms and informational.
Give a short label (2-6 words).

Conditions:
{items}

Answer with JSON only: {{"conditions": [{{"field": "...", "nature": "...", "owner_linked": false, "owner_exemption_max_units": null, "owner_units_clause": null, "property_types_targeted": [], "affordable_targeted": false, "situation": null, "references": null, "label": "..."}}]}}"""

V6_FIELDS = ("nature", "owner_linked", "owner_exemption_max_units", "owner_units_clause", "property_types_targeted",
             "affordable_targeted", "situation", "references", "label")


def _verbatim(clause, text):
    return isinstance(clause, str) and bool(clause.strip()) and \
        " ".join(clause.lower().split()) in " ".join(text.lower().split())


def validate_v6(c, text):
    rejected = []
    nature = c.get("nature") if c.get("nature") in NATURES else "informational"
    if c.get("nature") not in NATURES:
        rejected.append(f"nature {c.get('nature')!r}")
    um, clause = c.get("owner_exemption_max_units"), c.get("owner_units_clause")
    ok = isinstance(um, int) and not isinstance(um, bool) and um > 0 and _verbatim(clause, text)
    if um is not None and not ok:
        rejected.append(f"owner_units_clause {clause!r} not verbatim in the text")
    types = [t for t in PROPERTY_TYPES if t in (c.get("property_types_targeted") or [])]
    rejected += [f"property type {t!r}" for t in (c.get("property_types_targeted") or []) if t not in PROPERTY_TYPES]
    scoped = nature in ("positive_limit", "exemption")
    sit = c.get("situation") if c.get("situation") in SITUATIONS and scoped else None
    if nature == "positive_limit" and sit not in ("restricted_coverage", "references_coverage"):
        sit = "restricted_coverage"
    if nature == "exemption" and sit in (None, "restricted_coverage"):
        sit = "ordinary"
    ref = c.get("references") if sit == "references_coverage" and isinstance(c.get("references"), str) else None
    return {"nature": nature, "owner_linked": bool(c.get("owner_linked")) and scoped,
            "owner_exemption_max_units": um if ok else None, "owner_units_clause": clause.strip() if ok else None,
            "property_types_targeted": types if scoped else [],
            "affordable_targeted": bool(c.get("affordable_targeted")) and nature == "exemption",
            "situation": sit, "references": ref, "label": c.get("label") or "condition"}, rejected


POSITIVE_W = re.compile(r"\b(only|solely|limited to|exclusively)\b", re.I)
NARROW_W = re.compile(r"\b(subsidi[sz]ed|subsidy|subsidies|affordable|income[- ]restricted|IDP|DND|inclusionary|"
                      r"program|public housing)\b", re.I)
EXEMPT_W = re.compile(r"\b(exempt\w*|does not apply|do not apply|shall not apply|not apply|excluded|excludes?|"
                      r"except|not covered|not subject|instead|already subject|not rent controlled|not regulated)\b",
                      re.I)
OWNER_W = re.compile(r"\b(owner[- ]occupi\w+|owner occupancy|owners? (?:of record )?(?:lives?|resides?|resided|"
                     r"occupies|occupied|shares?)|landlord (?:lives?|resides?|resided)|natural persons?|family trust|"
                     r"small landlords?|mom and pop|owner-based|REIT|real estate (?:investment )?trust|corporations?)\b",
                     re.I)
TYPE_W = {t: re.compile(rx, re.I) for t, rx in (
    ("single_family", r"single[- ]family|one[- ]family|1-family"),
    ("condo", r"condominium|\bcondos?\b"),
    ("townhome", r"townho(?:me|use)s?"),
    ("mobile_home", r"mobile ?homes?"),
    ("duplex", r"duplex|two[- ]family|2-family|two[- ]unit|two separate dwelling units"),
    ("triplex", r"triplex|three[- ]family|3-family"),
    ("room_in_owner_home", r"rooms? in (?:an |the )?owner|one additional person|owner's roommate|roomer"),
    ("hotel", r"hotels?|motels?|transient|tourist|guest house"),
    ("care_facility", r"care facilit|hospitals?|nursing|residential care|medical"),
    ("dormitory", r"dormitor|fraternity|sorority"))}
AFFORDABLE_W = re.compile(r"\b(affordable|deed[- ]restricted|subsidi[sz]ed|low[- ]income|moderate[- ]income)\b", re.I)
UNUSUAL_W = re.compile(r"\b(seasonal|vacation|transient|shares? (?:a )?kitchen|shared (?:kitchen|bath)|"
                       r"detention|roommate|dormitor\w*|care facilit\w*|by application)\b", re.I)


def heuristic_v6(cond):
    text, field = cond.get("text") or "", cond.get("field") or "exemptions"
    effect = cond.get("effect") or heuristic(field, text)["effect"]
    sit = cond.get("situation")
    if effect in ("modifies_terms", "informational"):
        nature = effect
    elif sit == "restricted_coverage":
        nature = "positive_limit"
    elif sit == "references_coverage":
        nature = "exemption" if EXEMPT_W.search(text) else "positive_limit"
    elif POSITIVE_W.search(text) and NARROW_W.search(text) and not EXEMPT_W.search(text):
        nature = "positive_limit"
    else:
        nature = "exemption"
    if nature == "exemption" and sit not in ("unusual", "ordinary", "references_coverage"):
        sit = "unusual" if UNUSUAL_W.search(text) else "ordinary"
    owner = nature == "exemption" and bool(OWNER_W.search(text))
    um, clause = cond.get("units_max"), cond.get("units_clause")
    bound = owner and isinstance(um, int)
    types = [t for t, rx in TYPE_W.items() if rx.search(text)] if nature == "exemption" else []
    if nature == "exemption" and not types and cond.get("can_exclude_apartment_building") is False:
        types = ["other"]
    fields, _ = validate_v6({"nature": nature, "owner_linked": owner, "owner_exemption_max_units": um if bound else None,
                             "owner_units_clause": clause, "property_types_targeted": types,
                             "affordable_targeted": bool(AFFORDABLE_W.search(text)), "situation": sit,
                             "references": cond.get("references"), "label": cond.get("label")}, text)
    if bound and fields["owner_exemption_max_units"] is None and cond.get("units_clause") is None:
        fields["owner_exemption_max_units"] = um
    return fields


def _claude_v6(rule, texts):
    items = "\n".join(f"- field={f}: {t}" for f, t in texts)
    raw, label = _ask(PROMPT_V6.format(title=rule.get("title", ""), requirement=rule.get("requirement", ""),
                                       items=items))
    if "{" not in raw:
        raise ValueError(f"no JSON in model reply: {raw[:120]!r}")
    data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    if len(data["conditions"]) != len(texts):
        raise ValueError(f"{len(data['conditions'])} classifications for {len(texts)} conditions")
    return [dict(validate_v6(c, t)[0], field=f) for (f, t), c in zip(texts, data["conditions"])], label


def classify_v6(rules, use_api=False, use_cache=True):
    stored = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    cache = stored if use_cache else {}
    log, api_error, dirty = [], None, False
    for r in rules:
        texts = _texts(r)
        if not texts:
            r["_conditions"] = None
            continue
        conds = r.get("_conditions") or [{"field": f, "text": t} for f, t in texts]
        key = _key(r, texts, PROMPT_VERSION_V6)
        entry, source = cache.get(key), None
        if entry is None and use_api and api_error is None:
            for attempt in range(3):
                try:
                    out, label = _claude_v6(r, texts)
                    entry = {"classifier": label, "prompt_version": PROMPT_VERSION_V6, "conditions": out}
                    stored[key], dirty = entry, True
                    break
                except Exception as e:
                    msg = f"{type(e).__name__}: {str(e)[:160]}"
                    if attempt < 2 and "no ANTHROPIC_API_KEY" not in msg:
                        import time
                        time.sleep(5)
                        continue
                    if "no ANTHROPIC_API_KEY" in msg or any(w in msg.lower() for w in ("rate", "quota", "429", "credit")):
                        api_error = msg
        if entry is not None and len(entry["conditions"]) == len(conds):
            source = f"v6 ({entry['classifier']})"
        for i, c in enumerate(conds):
            c.setdefault("text", texts[i][1])
            v5 = c.setdefault("_v5", {k: c.get(k) for k in ("situation", "references", "label")})
            v6 = validate_v6(entry["conditions"][i], c["text"])[0] if source else heuristic_v6({**c, **v5})
            c.update(v6)
            c["v6_source"] = source or "heuristic_v6"
        r["_conditions"] = conds
        log.append({"team_rule_id": r["team_rule_id"], "key": key, "source": source or "heuristic_v6",
                    "conditions": [{k: c.get(k) for k in ("field",) + V6_FIELDS} for c in conds]})
    if dirty:
        CACHE.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n")
    return log, api_error


def main():
    from .prepare import prepare_rules
    from .rules import load_rules
    rules, source, _ = load_rules()
    rules, _ = prepare_rules(rules)
    log, err = classify(rules)
    used = sum(1 for e in log if not e["classifier"].startswith("heuristic"))
    print(f"classified {used}/{len(log)} rules with conditions from {source}; cache: {CACHE}" + (f"; {err}" if err else ""))


if __name__ == "__main__":
    main()
