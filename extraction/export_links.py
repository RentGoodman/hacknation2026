import hashlib
import itertools
import json
import sys

cache = json.load(open(sys.argv[1]))
rules = json.load(open("out/rules.json"))["rules"]


def rule_key(r):
    digest = hashlib.sha1(f"{r['category']}\n{r['quoted_span']}".encode()).hexdigest()[:12]
    return f"{r['source_doc_id']}:{digest}"


ids = {rule_key(r): r["team_rule_id"] for r in rules}
out, dropped = [], 0
for group in cache.values():
    for l in group["links"]:
        a, b = ids.get(l["governing"]), ids.get(l["yielding"])
        if not a or not b:
            dropped += 1
            continue
        out.append({"from": a, "to": b, "type": "supersedes", "uncertain": l["uncertain"],
                    "explanation": l["explanation"]})
    for c in group["conflicts"]:
        involved = [ids[k] for k in c["rules"] if k in ids]
        if len(involved) < len(c["rules"]):
            dropped += 1
        for a, b in itertools.combinations(involved, 2):
            out.append({"from": a, "to": b, "type": "conflicts", "uncertain": False, "explanation": c["note"]})
json.dump({"source": sys.argv[1], "links": out}, open("out/links.json", "w"), indent=2, ensure_ascii=False)
print(f"wrote out/links.json: {len(out)} links ({dropped} cache entries with rules not in out/rules.json)")
