import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from .rules import ROOT, load_buildings
from .verdict import DEFAULT_AS_OF, lookups, to_date

CATEGORIES = ["rent_increase_limits", "just_cause_eviction", "security_deposits", "application_screening_fees",
              "screening_restrictions", "algorithmic_rent_setting"]
SCHEMA_PATH = ROOT / "starter pack" / "schema" / "rule_record.schema.json"
PART1_KEYS = ["summary", "construction_date_basis", "built_on_or_before", "built_after", "min_building_age_years",
              "min_units", "max_units", "owner_conditions", "other_conditions"]
DOC_ID = "HOUR16"
ID_PREFIX = "h16-"
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
_NUM = r"(\d[\d,]*|" + "|".join(WORDS) + r")"
_UNIT = r"(?:dwelling |residential |rental |housing )*(?:units?|apartments?|dwellings?)"
_MONTH = "(" + "|".join(MONTHS) + ")"
_DATE = _MONTH + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"

OPERATIVE = re.compile(r"\b(shall not|shall|must not|must|may not|is prohibited|are prohibited|prohibited)\b", re.I)
SKIP_TITLE = re.compile(r"definition|purpose|finding|short title|effective|severab|enforcement|penalt|repeal|"
                        r"construction", re.I)
SCOPE_TITLE = re.compile(r"applicab|scope|coverage|covered|definition", re.I)
SECTION = re.compile(r"^\s*(?:Section|Sec\.|SECTION|§)\s*([\w.\-]+?)\.?\s+(.*\S)\s*$")
KEYWORDS = {
    "rent_increase_limits": ["rent increase", "increase the rent", "increase rent", "raise the rent", "rent cap",
                             "rent control", "rent stabilization", "allowable increase"],
    "just_cause_eviction": ["evict", "just cause", "terminate a tenancy", "terminates a tenancy", "end the tenancy",
                            "notice to quit", "termination of tenancy", "relocation", "displace"],
    "security_deposits": ["security deposit", "last month's rent", "last month rent", "deposit"],
    "application_screening_fees": ["application fee", "screening fee", "fee to apply", "background check fee"],
    "screening_restrictions": ["criminal history", "source of income", "credit score", "credit history", "screening",
                               "prospective tenant", "applicant", "tenant selection"],
    "algorithmic_rent_setting": ["algorithm", "pricing software", "revenue management", "rent-setting software",
                                 "coordinated pricing"],
}



def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def span_is_verbatim(span, text):
    s = norm_ws(span)
    return len(s) >= 20 and s in norm_ws(text)


def _n(w):
    w = w.lower().replace(",", "")
    return int(w) if w.isdigit() else WORDS[w]


def _date(m_name, day, year):
    return date(int(year), MONTHS[m_name.lower()], int(day))


def parse_effective(text):
    t = norm_ws(text)
    for pat in (r"(?:take|takes|taken|become|becomes) effect (?:on|upon|beginning|as of)?\s*" + _DATE,
                r"effective (?:on|date of|as of|beginning)?\s*" + _DATE,
                r"effective\s+" + _DATE):
        m = re.search(pat, t, re.I)
        if m:
            return _date(*m.groups()).isoformat()
    m = re.search(r"effective (?:on |date of |as of )?(\d{4}-\d{2}-\d{2})", t, re.I)
    return m.group(1) if m else None


def parse_units(text):
    t = norm_ws(text)
    lo = hi = None
    pats_lo = [(rf"{_NUM} or more {_UNIT}", 0), (rf"at least {_NUM} {_UNIT}", 0),
               (rf"(?<!no )(?<!not )more than {_NUM} {_UNIT}", 1), (rf"containing {_NUM} or more", 0), (rf"{_NUM}\+ {_UNIT}", 0),
               (rf"(?:minimum|min\.?) of {_NUM} {_UNIT}", 0)]
    for pat, add in pats_lo:
        m = re.search(pat, t, re.I)
        if m:
            lo = _n(m.group(1)) + add
            break
    pats_hi = [(rf"{_NUM} or (?:fewer|less) {_UNIT}", 0), (rf"(?:fewer|less) than {_NUM} {_UNIT}", -1),
               (rf"no more than {_NUM} {_UNIT}", 0), (rf"at most {_NUM} {_UNIT}", 0),
               (rf"not more than {_NUM} {_UNIT}", 0)]
    for pat, add in pats_hi:
        m = re.search(pat, t, re.I)
        if m:
            hi = _n(m.group(1)) + add
            break
    return lo, hi


def parse_built(text):
    t = norm_ws(text)
    on_or_before = after = age = None
    when = rf"(?:{_DATE}|(\d{{4}}))"

    verbs = r"(?:built|constructed|completed|first occupied|issued a certificate of occupancy)"
    m = re.search(rf"{verbs} (?:on or )?before {when}", t, re.I)
    if m:
        on_or_before = _cutoff(m, strictly_before="on or before" not in m.group(0).lower())
    m = re.search(rf"{verbs} (?:in or|on or) after {when}", t, re.I)
    if m:
        after = _cutoff(m, strictly_before=True)
    else:
        m = re.search(rf"{verbs} after {when}", t, re.I)
        if m:
            after = _cutoff(m, strictly_before=False)
    m = _AGE.search(t)
    if m:
        age = _n(m.group(1))
    basis = "certificate_of_occupancy" if re.search(r"certificate of occupancy", t, re.I) else (
        "year_built" if (on_or_before or after) else None)
    return (on_or_before.isoformat() if on_or_before else None, after.isoformat() if after else None, age, basis)


_AGE = re.compile(rf"{_NUM}\s+years? old or older|at least {_NUM}\s+years? old|more than {_NUM}\s+years? old", re.I)


def _cutoff(m, strictly_before):
    g = m.groups()
    month, day, year, yr = g[-4], g[-3], g[-2], g[-1]
    if month:
        d = _date(month, day, year)
        return d - timedelta(days=1) if strictly_before else d
    y = int(yr)
    return date(y - 1, 12, 31) if strictly_before else date(y, 12, 31)


def parse_coverage(text, jurisdiction, owner_text=None):
    lo, hi = parse_units(text)
    before, after, age, basis = parse_built(text)
    if all(x is None for x in (lo, hi, before, after, age)):
        return None
    bits = []
    if lo is not None:
        bits.append(f"{lo} or more units")
    if hi is not None:
        bits.append(f"at most {hi} units")
    if before:
        bits.append(f"built on or before {before}")
    if after:
        bits.append(f"built after {after}")
    if age is not None:
        bits.append(f"at least {age} years old")
    return {"summary": f"Residential buildings in {jurisdiction} with " + ", ".join(bits) + ".",
            "construction_date_basis": basis, "built_on_or_before": before, "built_after": after,
            "min_building_age_years": age, "min_units": lo, "max_units": hi,
            "owner_conditions": owner_text, "other_conditions": None}



def split_sections(text):
    sections, cur = [], None
    for line in text.splitlines():
        m = SECTION.match(line)
        if m:
            if cur:
                sections.append(cur)
            label, head = m.group(1), m.group(2)
            body = ""
            if "." in head:
                h, _, rest = head.partition(". ")
                head, body = (h, rest) if rest else (head.rstrip("."), "")
            cur = [label, head.rstrip("."), body]
        elif cur:
            cur[2] += " " + line
    if cur:
        sections.append(cur)
    return [(a, b, norm_ws(c)) for a, b, c in sections]


def split_sentences(s):
    return [x.strip() for x in re.split(r"(?<=[.;])\s+(?=[A-Z])", norm_ws(s)) if x.strip()]


def guess_category(text):
    scores = {c: sum(text.lower().count(k) for k in kws) for c, kws in KEYWORDS.items()}
    best = max(CATEGORIES, key=lambda c: (scores[c], -CATEGORIES.index(c)))
    return best if scores[best] else None


def ordinance_title(text):
    for line in text.splitlines():
        l = line.strip()
        if re.search(r"\b(ordinance|act|law|chapter|bylaw)\b", l, re.I) and not l.lower().startswith(
                ("notice", "section", "sec.", "this ")) and len(l) < 120:
            return l.title() if l.isupper() else l
    return "New ordinance"


def _key_value(body):
    m = re.search(r"(\d+|" + "|".join(WORDS) + r")\s+months?(?:'s?|s')?\s+(?:of\s+)?rent|\$[\d,]+(?:\.\d+)?|"
                  r"\d+(?:\.\d+)?\s*(?:percent|%)|\d+\s+days", body, re.I)
    return m.group(0) if m else None


def extract_deterministic(text, jurisdiction, effective=None, source_url=""):
    secs = split_sections(text)
    if not secs:
        secs = [(str(i), "", norm_ws(p)) for i, p in enumerate(re.split(r"\n\s*\n", text), 1) if p.strip()]
    title = ordinance_title(text)
    eff = effective or parse_effective(text)
    scope_text = " ".join(b for _, h, b in secs if SCOPE_TITLE.search(h))
    exempt = [s for s in split_sentences(scope_text) if re.search(r"does not apply|exempt|shall not apply", s, re.I)]
    owner = next((s for s in exempt if re.search(r"owner", s, re.I)), None)
    rules, rejected = [], []
    for label, head, body in secs:
        if SKIP_TITLE.search(head) or not OPERATIVE.search(body):
            continue
        sents = split_sentences(body)
        op = next((s for s in sents if OPERATIVE.search(s)), None)
        cat = guess_category(f"{head} {body}")
        if cat is None:
            rejected.append({"section": label, "heading": head, "reason": "no category keyword matched"})
            continue
        span = op if op and len(op) >= 20 else norm_ws(body)[:200]
        if not span_is_verbatim(span, text):
            rejected.append({"section": label, "heading": head, "reason": "quoted_span not found in the file"})
            continue
        cov = parse_coverage(body, jurisdiction, owner) or parse_coverage(scope_text, jurisdiction, owner)
        rules.append({
            "jurisdiction": jurisdiction, "level": "city" if "," in jurisdiction else "state", "category": cat,
            "title": f"{title} - {head}" if head else title,
            "requirement": " ".join(sents[:2])[:500], "key_value": _key_value(body),
            "coverage_conditions": cov if cov else {k: None for k in PART1_KEYS},
            "exemptions": " ".join(exempt) or None, "overrides": [], "interaction": None,
            "citation": f"{title}, Section {label}", "quoted_span": span, "confidence": 0.5,
            "conflict_flag": False, "conflict_note": None})
    return rules, rejected



PROMPT = """You extract landlord-tenant rules from a newly published ordinance.
Jurisdiction: {jurisdiction}
Return JSON only: {{"rules": [ ... ]}}. One rule per operative section (a duty or prohibition on landlords).
Each rule follows this schema (fields of starter pack/schema/rule_record.schema.json):
- category: one of {categories}
- title, requirement (one or two plain sentences), key_value (headline number or null), citation (section cite)
- coverage_conditions: {{"summary": str, "construction_date_basis": "year_built"|"certificate_of_occupancy"|null,
  "built_on_or_before": "YYYY-MM-DD"|null, "built_after": "YYYY-MM-DD"|null, "min_building_age_years": int|null,
  "min_units": int|null, "max_units": int|null, "owner_conditions": str|null, "other_conditions": str|null}}
  (net of exemptions; "six or more units" means min_units 6; "built before 1980" means built_on_or_before 1979-12-31)
- exemptions (str|null), effective_date (YYYY-MM-DD|null), confidence (0 to 1)
- quoted_span: an exact copy of at least 20 characters of the ordinance text that supports the rule.
Do not invent text. Ordinance text:
---
{text}
---"""


def extract_claude(text, jurisdiction, effective=None):
    from .classify_conditions import _ask
    raw, label = _ask(PROMPT.format(jurisdiction=jurisdiction, categories=", ".join(CATEGORIES), text=text[:30000]))
    if "{" not in raw:
        raise ValueError(f"no JSON in model reply: {raw[:120]!r}")
    data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    eff = effective or parse_effective(text)
    rules, rejected = [], []
    for r in data.get("rules", []):
        why = None
        if r.get("category") not in CATEGORIES:
            why = f"category {r.get('category')!r} not in the closed list"
        elif not r.get("quoted_span") or not span_is_verbatim(r["quoted_span"], text):
            why = "quoted_span not found in the file"
        if why:
            rejected.append({"title": r.get("title"), "reason": why})
            continue
        cov = r.get("coverage_conditions")
        cov = {k: (cov or {}).get(k) for k in PART1_KEYS} if isinstance(cov, dict) else {k: None for k in PART1_KEYS}
        rules.append({
            "jurisdiction": jurisdiction, "level": "city" if "," in jurisdiction else "state",
            "category": r["category"], "title": r.get("title") or r["category"],
            "requirement": r.get("requirement") or "", "key_value": r.get("key_value"),
            "coverage_conditions": cov, "exemptions": r.get("exemptions"), "overrides": [], "interaction": None,
            "citation": r.get("citation") or "", "quoted_span": norm_ws(r["quoted_span"]),
            "confidence": r.get("confidence"), "conflict_flag": False, "conflict_note": None,
            "_effective": r.get("effective_date")})
    return rules, rejected, label, eff



_SNAPSHOT = ["out/rules.json", "out/changes.json", "out/lookups.json", "out/engine_run.json",
             "out/overrides_audit.md", "corpus_extra/corpus_manifest.csv", "corpus_extra/manifest_extra.csv"]


def extract_part1(path, jurisdiction):
    if not shutil.which("uv"):
        raise RuntimeError("uv is not installed")
    snap = {p: (ROOT / p).read_bytes() for p in _SNAPSHOT if (ROOT / p).exists()}
    extra_before = {p.name for p in (ROOT / "corpus_extra").glob("DX*.txt")}
    try:
        proc = subprocess.run([sys.executable, "-m", "extraction.ingest_new", "--jurisdiction", jurisdiction,
                               "--file", str(path), "--test-id", "T6_part1"], cwd=ROOT, capture_output=True, text=True,
                              timeout=1800)
        if proc.returncode:
            raise RuntimeError((proc.stderr or proc.stdout).strip().splitlines()[-1] if (proc.stderr or proc.stdout)
                               else f"exit code {proc.returncode}")
        before = {r["team_rule_id"] for r in _rules_list(snap["out/rules.json"].decode())}
        added = [r for r in _rules_list((ROOT / "out/rules.json").read_text()) if r["team_rule_id"] not in before]
    finally:
        for p, data in snap.items():
            (ROOT / p).write_bytes(data)
        for p in (ROOT / "corpus_extra").glob("DX*.txt"):
            if p.name not in extra_before:
                p.unlink()
    if not added:
        raise RuntimeError("Part 1 command produced no new rule")
    return added


def _rules_list(text):
    d = json.loads(text)
    return d["rules"] if isinstance(d, dict) else d



def finalize(rules, text, jurisdiction, effective, source_url, as_of=DEFAULT_AS_OF, start=1):
    out = []
    for i, r in enumerate(rules, start):
        r = dict(r)
        eff = effective or r.get("effective_date") or r.get("_effective") or parse_effective(text)
        r.pop("_effective", None)
        r["team_rule_id"] = f"{ID_PREFIX}{i:04d}"
        r["effective_date"] = eff
        r["status"] = "not_yet_effective" if eff and to_date(eff) > to_date(as_of) else "in_force"
        r["source_doc_id"] = DOC_ID
        r["source_url"] = source_url
        out.append(r)
    return out


def default_dates(effective, before, after):
    if effective:
        d = date.fromisoformat(effective)
        return before or (d - timedelta(days=1)).isoformat(), after or d.isoformat()
    return before, after


def compute_affected(buildings, base_rules, new_rules, before, after):
    ids = {r["team_rule_id"] for r in new_rules}
    if before:
        lb = lookups(buildings, base_rules + new_rules, before)
    else:
        before = after = after or DEFAULT_AS_OF
        lb = lookups(buildings, base_rules, before)
    la = lookups(buildings, base_rules + new_rules, after)

    def pick(L, aid):
        return {e["team_rule_id"]: e["result"] for e in L.get(aid, []) if e["team_rule_id"] in ids}

    applies, unknown, conflicts, pairs = [], [], [], {}
    for aid in sorted(buildings):
        pb, pa = pick(lb, aid), pick(la, aid)
        res = []
        for i in sorted(ids):
            rb, ra = pb.get(i, "omitted"), pa.get(i, "omitted")
            if rb in ("omitted", "not_yet_effective") and ra in ("applies", "unknown"):
                res.append(ra)
            if rb != ra:
                pairs.setdefault(aid, {})[i] = [rb, ra]
        if "applies" in res:
            applies.append(aid)
        elif "unknown" in res:
            unknown.append(aid)
        if any(e["team_rule_id"] in ids and e.get("conflict_flag") for e in la.get(aid, [])):
            conflicts.append(aid)
    return {"applies": applies, "unknown": unknown, "affected": sorted(applies + unknown), "conflicts": conflicts,
            "pairs": pairs, "before": before, "after": after}


def city_of(b):
    return b.get("legal_city") or b.get("legal_city_candidate")


def build_entry(res, buildings, new_rules, jurisdiction, effective, extractor, rejected,
                invalidated_findings=None):
    from collections import Counter
    by_city = Counter(city_of(buildings[a]) for a in res["affected"])
    ids = [r["team_rule_id"] for r in new_rules]
    invalidated_findings = invalidated_findings or []
    notes = (f"ingest_new ({extractor}): {DOC_ID} ({jurisdiction}) added {len(ids)} rule(s) {', '.join(ids) or 'none'}"
             f"{', effective ' + effective if effective else ', no effective date found'}. Compared "
             f"{res['before']} with {res['after']}; affected = a new rule goes from omitted or not_yet_effective to "
             f"applies or unknown: {len(res['affected'])} addresses (applies {len(res['applies'])}, unknown "
             f"{len(res['unknown'])}; by city: {dict(sorted(by_city.items()))}). Unknown, listed separately: "
             f"{', '.join(res['unknown']) or 'none'}. Conflict flags on new rules: {len(res['conflicts'])}."
             + (f" Invalidated no-rule findings: "
                f"{', '.join(f['jurisdiction'] + ' / ' + f['category'] for f in invalidated_findings)}."
                if invalidated_findings else " Invalidated no-rule findings: none.")
             + (f" Rejected sections: {len(rejected)} ({'; '.join(x.get('reason', '') for x in rejected)})."
                if rejected else ""))
    return {"affected_address_ids": res["affected"], "conflict_flag_address_ids": res["conflicts"],
            "rule_ids": ids, "source_doc_id": DOC_ID, "jurisdiction": jurisdiction, "effective_date": effective,
            "invalidated_no_rule_findings": invalidated_findings,
            "compare": {"before": res["before"], "after": res["after"], "basis": "effective_date" if effective
                        else "without vs with new rules"},
            "notes": notes}, dict(sorted(by_city.items()))


def write_changes(path, entry, test_id="T6"):
    data = json.loads(path.read_text()) if path.exists() else {}
    data[test_id] = entry
    path.write_text(json.dumps(data, indent=2) + "\n")


def recompute_entry(buildings, base_rules, path, test_id="T6"):
    data = json.loads(Path(path).read_text())
    new = data.get("rules") or []
    if not new:
        return None
    jur = data.get("jurisdiction") or new[0]["jurisdiction"]
    eff = data.get("effective_date") or (sorted(r["effective_date"] for r in new if r.get("effective_date")) or [None])[0]
    before, after = default_dates(eff, None, None)
    all_rules = annotate_precedence(base_rules + new)
    base_part = [r for r in all_rules if not r["team_rule_id"].startswith(ID_PREFIX)]
    new_part = [r for r in all_rules if r["team_rule_id"].startswith(ID_PREFIX)]
    res = compute_affected(buildings, base_part, new_part, before, after)
    invalidated = invalidated_no_rule_findings(new_part, load_no_rule_findings())
    entry, _ = build_entry(res, buildings, new_part, jur, eff, data.get("extractor") or "stored",
                           data.get("rejected") or [], invalidated)
    return entry


def annotate_precedence(rules):
    from .precedence import DEFAULT
    from .prepare import is_ma_40p

    out = []
    for rule in rules:
        r = dict(rule)
        if is_ma_40p(r):
            r["_annotation"] = {**DEFAULT, **(r.get("_annotation") or {}),
                                "may_preempt_local": True, "bars_local_cap": True}
        out.append(r)
    return out


def load_no_rule_findings():
    data = json.loads((ROOT / "out" / "rules.json").read_text(encoding="utf-8"))
    return [f for f in data.get("no_rule_findings", []) if all(
        str(f.get(k) or "").strip() for k in ("jurisdiction", "category", "quoted_span")
    ) and (f.get("citation") or f.get("basis_citation"))]


def invalidated_no_rule_findings(new_rules, findings):
    cells = {(r.get("jurisdiction"), r.get("category")) for r in new_rules
             if r.get("status") in ("in_force", "not_yet_effective")}
    out = []
    for f in findings:
        if (f.get("jurisdiction"), f.get("category")) not in cells:
            continue
        out.append({
            "jurisdiction": f["jurisdiction"], "category": f["category"],
            "citation": f.get("citation") or f.get("basis_citation"),
            "source_doc_id": f.get("source_doc_id") or f.get("doc_id"),
        })
    return sorted(out, key=lambda f: (f["jurisdiction"], f["category"], f.get("source_doc_id") or ""))


def run(args):
    path = Path(args.file)
    text = path.read_text(encoding="utf-8", errors="replace")
    log, rejected, extractor, rules = [], [], None, None
    order = ["part1", "claude", "deterministic"] if args.extractor == "auto" else [args.extractor]
    effective = args.effective
    for name in order:
        try:
            if name == "part1":
                if args.dry_run or args.extractor == "auto" and not _has_key():
                    raise RuntimeError("skipped (dry run or no API key)")
                got = extract_part1(path, args.jurisdiction)
                rules = [{k: v for k, v in r.items() if k not in ("team_rule_id", "source_doc_id", "source_url")}
                         for r in got]
                rejected = []
            elif name == "claude":
                rules, rejected, _, _ = extract_claude(text, args.jurisdiction, effective)
            else:
                rules, rejected = extract_deterministic(text, args.jurisdiction, effective, str(path))
            extractor = name
            break
        except Exception as e:
            log.append(f"{name}: {type(e).__name__}: {e}")
    if rules is None:
        raise SystemExit("no extractor worked: " + " | ".join(log))
    new_rules = finalize(rules, text, args.jurisdiction, effective, str(path))
    effective = effective or (sorted({r["effective_date"] for r in new_rules if r.get("effective_date")}) or [None])[0]
    if effective and len(effective) < 10:
        effective = {4: "{}-01-01", 7: "{}-01"}[len(effective)].format(effective)
    for r in new_rules:
        if not r["effective_date"]:
            r["effective_date"] = effective
            r["status"] = "not_yet_effective" if effective and to_date(effective) > to_date(DEFAULT_AS_OF) else "in_force"
    out_rules = ROOT / args.rules_out
    if args.rules_out_abs:
        out_rules = Path(args.rules_out)
    if not args.dry_run:
        out_rules.parent.mkdir(parents=True, exist_ok=True)
        out_rules.write_text(json.dumps({"jurisdiction": args.jurisdiction, "effective_date": effective,
                                         "extractor": extractor, "rejected": rejected,
                                         "rules": new_rules}, indent=2) + "\n")

    from .run import evaluation_rules
    base = evaluation_rules(fetch=False)
    all_rules = annotate_precedence(base + new_rules)
    base_part = [r for r in all_rules if not r["team_rule_id"].startswith(ID_PREFIX)]
    new_part = [r for r in all_rules if r["team_rule_id"].startswith(ID_PREFIX)]
    before, after = default_dates(effective, args.as_of_before, args.as_of_after)
    buildings = load_buildings()
    res = compute_affected(buildings, base_part, new_part, before, after)
    invalidated = invalidated_no_rule_findings(new_part, load_no_rule_findings())
    entry, by_city = build_entry(res, buildings, new_part, args.jurisdiction, effective, extractor, rejected,
                                 invalidated)
    summary = {"extractor": extractor, "extractor_log": log,
               "rules_out": None if args.dry_run else _rel(out_rules), "new_rule_ids":
               [r["team_rule_id"] for r in new_part], "rejected": rejected, "effective_date": effective,
               "as_of_before": res["before"], "as_of_after": res["after"], "affected": len(res["affected"]),
               "applies": len(res["applies"]), "unknown": len(res["unknown"]), "unknown_ids": res["unknown"],
               "conflicts": len(res["conflicts"]), "by_city": by_city}
    if args.summary_out:
        p = Path(args.summary_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"T6": entry, "summary": summary}, indent=2) + "\n")
    if not args.dry_run:
        write_changes(Path(args.changes), entry, args.test_id)
    return entry, summary


def _rel(p):
    try:
        return str(Path(p).relative_to(ROOT))
    except ValueError:
        return str(p)


def _has_key():
    import os
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingest a new ordinance and list the affected addresses (T6).")
    ap.add_argument("file")
    ap.add_argument("--jurisdiction", required=True, help='"CA" or "City, ST"')
    ap.add_argument("--effective", help="YYYY-MM-DD; default: parsed from the text")
    ap.add_argument("--as-of-before")
    ap.add_argument("--as-of-after")
    ap.add_argument("--rules-out", default="out/rules_hour16.json")
    ap.add_argument("--changes", default=str(ROOT / "out" / "changes.json"))
    ap.add_argument("--test-id", default="T6")
    ap.add_argument("--extractor", default="auto", choices=["auto", "part1", "claude", "deterministic"])
    ap.add_argument("--summary-out", help="also write {T6 entry, summary} to this JSON file")
    ap.add_argument("--dry-run", action="store_true", help="do not write the change test entry")
    args = ap.parse_args(argv)
    args.rules_out_abs = Path(args.rules_out).is_absolute()
    entry, s = run(args)
    print(f"extractor: {s['extractor']}" + "".join(f"\n  fallback: {m}" for m in s["extractor_log"]))
    action = "evaluated (dry run; no rule file written)" if args.dry_run else f"written to {s['rules_out']}"
    print(f"rules: {len(s['new_rule_ids'])} {action}; rejected {len(s['rejected'])}")
    for x in s["rejected"]:
        print(f"  rejected: {x}")
    print(f"effective {s['effective_date']}; compared {s['as_of_before']} with {s['as_of_after']}")
    print(f"affected {s['affected']} (applies {s['applies']}, unknown {s['unknown']}), conflicts {s['conflicts']}, "
          f"by city {s['by_city']}")
    print("T6 entry not written (dry run)" if args.dry_run else f"{args.test_id} written to {args.changes}")


if __name__ == "__main__":
    main()
