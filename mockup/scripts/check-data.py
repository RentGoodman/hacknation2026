import csv
import json
from collections import Counter
from pathlib import Path
from source_bundle import load_sources, check_rule_sources

root = Path(__file__).resolve().parents[1]
pack = root / 'inputs'
out = root / 'dist/data'
data = json.loads((out / 'starter-data.json').read_text())
original = {r['address_id']: r for r in csv.DictReader((pack / 'data/sample_addresses.csv').open())}
properties = data['properties']
assert len(properties) == len(original) == 500
assert {p['id'] for p in properties} == original.keys()
for p in properties:
    for field, value in original[p['id']].items():
        if field != 'units':
            assert p[field] == value, (p['id'], field)
    assert p['units'] == (int(float(original[p['id']]['units'])) if original[p['id']]['units'] else None)
    assert p['year'] == (int(original[p['id']]['year_built']) if original[p['id']]['year_built'] else None)
    if p['coord']:
        assert p['geocode']['status'] == 'Match'
        assert p['coord'] == p['geocode']['coordinates']
    else:
        assert p['geocode']['status'] != 'Match'
assert sum(bool(p['coord']) for p in properties) == data['geocoded'] == 477
assert Counter(p['state'] for p in properties) == {'CA': 250, 'NJ': 140, 'MA': 110}
assert sum(p['year'] is None for p in properties) == 212
assert sum(p['units'] is None for p in properties) == 242
sources = {s['doc_id']: s for s in data['sources']}
assert data['sources'] == load_sources(root)
assert len(sources) == len(data['sources']), 'Duplicate source IDs'
for s in sources.values():
    if s['text_available']:
        assert s['text'] == (out / 'text' / (s['doc_id'] + '.txt')).read_text()
for reading in data['readings']:
    assert reading['quote'] in sources[reading['doc_id']]['text']
    assert reading['needs'] and reading['date_basis']
assert data['change_tests'] == json.loads((pack / 'dev/change_tests.json').read_text())
assert (out / 'sample_addresses.csv').read_bytes() == (pack / 'data/sample_addresses.csv').read_bytes()
print(f"Verified 500 original records, preserved missing facts, 477 matched locations, {len(sources)} source entries, 22 exact passages, and 5 original change tests.")

repo = root.parent
eng = json.loads((out / 'engine-data.js').read_text()[len('window.ENGINE_DATA = '):].rstrip().rstrip(';'))
base = json.loads((repo / 'out/lookups.json').read_text())
changes = json.loads((repo / 'out/changes.json').read_text())
rules = json.loads((repo / 'out/rules.json').read_text())['rules']
check_rule_sources(data['sources'], eng['rules'].values())
assert eng['dates'] == ['2025-12-31', '2026-01-02', '2026-10-01', '2027-07-02']
assert set(eng['buildings']) == original.keys() and len(eng['rules']) == len(rules)
assert set(eng['scheduled_changes']) <= original.keys()
assert all(step['date'] > eng['default_date'] and step['changes']
           for steps in eng['scheduled_changes'].values() for step in steps)
assert all(isinstance(r['event_only'], bool) and isinstance(r['subsidized_program'], bool)
           for r in eng['rules'].values())
assert all((r.get('plain_language') or {}).get('en') and (r.get('plain_language') or {}).get('es')
           for r in eng['rules'].values())
assert all(r.get('source_type') for r in eng['rules'].values())
assert any(r['subsidized_program'] for r in eng['rules'].values())
assert all(d.get('summary') and 15 <= len(d['summary'].split()) <= 25
           for row in eng['details'].values() for d in row.values())
assert all(d.get('reasoning') for row in eng['details'].values() for d in row.values())
assert isinstance(eng['no_rule_findings'], list)
assert any(d.get('fact_hint') for row in eng['details'].values() for d in row.values())
assert eng['default_date'] == '2026-10-01'
assert eng['t6_rehearsal']['summary']['affected'] == 45
assert eng['t6_rehearsal']['summary']['conflicts'] == 0
assert eng['acceptance']['selfcheck'] == '17/17'
assert eng['inferred_omissions']['counts']['pairs'] == 0
if 'version' in eng:
    import hashlib
    assert eng['version']['rules_sha256'] == hashlib.sha256((repo / 'out/rules.json').read_bytes()).hexdigest()
html = (root / 'dist/index.html').read_text()
app = (root / 'dist/app.js').read_text()
assert 'Not legal advice' in html
assert 'Tenant · your rights' in app and 'Landlord · your obligations' in app
assert 'Verification' in html
assert "'As of'} ${esc(shortDate(date()))}" in app
for a, entries in base['lookups'].items():
    got = eng['lookups'][base['as_of']][a]
    assert [(e['team_rule_id'], e['result'], e['explanation'], bool(e.get('conflict_flag'))) for e in entries] == \
        [(i, r, eng['texts'][t], bool(c)) for i, r, t, c in got], a
for t in ['T1', 'T2', 'T3', 'T4', 'T5']:
    assert eng['changes'][t] == changes[t], t
def res(d, a, rid):
    return next((r for i, r, *_ in eng['lookups'][d][a] if i == rid), None)
live = ('applies', 'unknown')
import sys
sys.path.insert(0, str(root.parent))
from engine.changes import map_test_rules

mapping = map_test_rules(json.loads((root.parent / 'out/rules.json').read_text())['rules'])


def flips(t, before, after):
    test = {'CA-ALG-01': 'T1', 'NJ-ALG-01': 'T3'}[t]
    rids = mapping.get(t, [])
    return all(any(res(before, a, rid) == 'not_yet_effective' and res(after, a, rid) in live for rid in rids)
               for a in changes[test]['affected_address_ids'])


assert flips('CA-ALG-01', '2025-12-31', '2026-01-02')
assert flips('NJ-ALG-01', '2026-10-01', '2027-07-02')
print(f"Verified engine data: {len(eng['rules'])} rules, {len(eng['dates'])} dates, lookups on {base['as_of']} identical to out/lookups.json, T1 and T3 flips.")
