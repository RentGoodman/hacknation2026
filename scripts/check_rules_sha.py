import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / 'out/rules.json'
CHANGES = ROOT / 'out/changes.json'
ENGINE_DATA = ROOT / 'mockup/dist/data/engine-data.js'


def load_engine_data(path):
    text = path.read_text(encoding='utf-8')
    head, sep, _ = text.partition('ENGINE_DATA')
    if not sep:
        raise ValueError(f'{path}: no ENGINE_DATA assignment')
    start = text.index('{', len(head) + len(sep))
    data, _ = json.JSONDecoder().raw_decode(text, start)
    return data


def main():
    expected = hashlib.sha256(RULES.read_bytes()).hexdigest()
    changes = json.loads(CHANGES.read_text(encoding='utf-8'))
    eng = load_engine_data(ENGINE_DATA)
    found = [
        ('out/changes.json _meta.rules_sha256', (changes.get('_meta') or {}).get('rules_sha256'), True),
        ('engine-data.js rules_sha256', eng.get('rules_sha256'), True),
        ('engine-data.js acceptance.rules_sha256', (eng.get('acceptance') or {}).get('rules_sha256'), False),
        ('engine-data.js version.rules_sha256', (eng.get('version') or {}).get('rules_sha256'), False),
    ]
    errors = []
    checked = 0
    for label, value, required in found:
        if value is None and not required:
            continue
        checked += 1
        if value != expected:
            errors.append(f'{label} = {value} (expected {expected})')
    for error in errors:
        print(f'check_rules_sha: {error}', file=sys.stderr)
    if errors:
        print('check_rules_sha: rules hash mismatch; regenerate the outputs with ./run.sh.', file=sys.stderr)
        return 1
    print(f'check_rules_sha: OK, {checked} fields equal sha256(out/rules.json) = {expected[:12]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
