import csv
import hashlib
import json
from pathlib import Path


def rows(path):
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def load_sources(root):
    repo = root.parent
    local = root / 'inputs/corpus'
    original = repo / 'starter pack/corpus'
    extra = repo / 'corpus_extra'
    originals = {r['doc_id']: r for r in rows(original / 'corpus_manifest.csv')}
    metadata = {r['doc_id']: r for r in rows(extra / 'manifest_extra.csv')}
    sources = []
    seen = set()
    for directory in (local, extra):
        for row in rows(directory / 'corpus_manifest.csv'):
            row = dict(row)
            doc_id = row['doc_id']
            if doc_id in seen:
                raise ValueError(f'Duplicate source: {doc_id}')
            seen.add(doc_id)
            if directory == extra:
                details = metadata.get(doc_id, {})
                if details.get('url') != row['url']:
                    raise ValueError(f'Supplemental source URL mismatch: {doc_id}')
                row['sha256'] = details.get('sha256', '')
                row['note'] = details.get('note', '')
            path = directory / row['text_file'] if row['text_file'] else None
            if path and not path.is_file() and directory == local:
                source_row = originals.get(doc_id, {})
                if any(source_row.get(k) != row.get(k) for k in ('url', 'sha256', 'retrieved_at', 'text_file')):
                    raise ValueError(f'Original capture mismatch: {doc_id}')
                path = original / row['text_file']
            if path and not path.is_file():
                raise ValueError(f'Missing declared source text: {doc_id}')
            text = path.read_text(encoding='utf-8') if path else None
            content_hash = hashlib.sha256(text.encode()).hexdigest() if text else None
            if directory == extra and text and row['sha256'] != content_hash:
                raise ValueError(f'Supplemental source hash mismatch: {doc_id}')
            sources.append({**row, 'text_available': bool(text), 'text': text,
                            'local_path': f'data/text/{doc_id}.txt' if text else None,
                            'content_hash': content_hash})
    for doc_id, details in sorted(metadata.items()):
        if doc_id in seen or details.get('capture') != 'yes':
            continue
        path = extra / f'{doc_id}.txt'
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        if details.get('sha256') != content_hash:
            raise ValueError(f'Supplemental source hash mismatch: {doc_id}')
        seen.add(doc_id)
        sources.append({
            'doc_id': doc_id,
            'jurisdictions': details.get('jurisdictions') or details.get('jurisdiction') or '',
            'url': details['url'], 'source_type': details.get('source_type', 'official'),
            'capture': details.get('capture', 'yes'), 'retrieved_at': details.get('retrieved_at', ''),
            'sha256': details.get('sha256', ''), 'text_file': path.name, 'status': 'ok',
            'note': details.get('note', ''), 'text_available': True, 'text': text,
            'local_path': f'data/text/{doc_id}.txt', 'content_hash': content_hash,
        })
    return sources


def check_rule_sources(sources, rules):
    available = {s['doc_id'] for s in sources if s['text']}
    missing = sorted({r['source_doc_id'] for r in rules if r['source_doc_id'] not in available})
    if missing:
        raise ValueError(f'Rules reference unavailable source text: {", ".join(missing)}')


def write_sources(sources, out):
    (out / 'text').mkdir(parents=True, exist_ok=True)
    for source in sources:
        if source['text']:
            (out / 'text' / f"{source['doc_id']}.txt").write_text(source['text'], encoding='utf-8')


def write_starter(data, out):
    payload = json.dumps(data, ensure_ascii=False)
    (out / 'starter-data.json').write_text(payload, encoding='utf-8')
    (out / 'starter-data.js').write_text('window.PARCEL_DATA = ' + payload.replace('</', '<\\/') + ';\n', encoding='utf-8')


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    out = root / 'dist/data'
    data = json.loads((out / 'starter-data.json').read_text())
    engine = json.loads((out / 'engine-data.js').read_text().split('=', 1)[1].strip().rstrip(';'))
    data['sources'] = load_sources(root)
    check_rule_sources(data['sources'], engine['rules'].values())
    write_sources(data['sources'], out)
    write_starter(data, out)
    print(f"Packaged {len(data['sources'])} sources; {sum(s['text_available'] for s in data['sources'])} texts; all {len(engine['rules'])} rules have source text.")
