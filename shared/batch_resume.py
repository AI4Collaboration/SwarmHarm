"""Batch metadata for population selection and explicitly retained attempts."""
import json
from pathlib import Path


def key(row):
    return tuple(row.get(k) for k in (
        'model', 'population', 'replicate', 'task', 'channel', 'scenario', 'mechanism'))


def settings(row):
    return {k: v for k, v in row.items() if k != 'source_sha256'}


def retained(root):
    path = Path(root)/'retained-attempts.json'
    if not path.is_file():
        return {}
    result = {}
    for attempt in json.loads(path.read_text())['attempts']:
        output = (Path(root)/attempt['path']).resolve()
        if not output.is_relative_to(Path(root).resolve()) or not output.is_dir():
            raise ValueError('Retained attempt is missing or outside its batch directory')
        identity = key(attempt['settings'])
        if identity in result:
            raise ValueError('Multiple retained attempts for the same condition')
        result[identity] = attempt
    return result


def write(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    temporary.replace(path)


def prepare(root, rows, resume=False):
    root = Path(root)
    saved = retained(root) if resume else {}
    selected = []
    for row in rows:
        previous = saved.get(key(row))
        if previous:
            if settings(previous['settings']) != settings(row):
                raise ValueError('Retained attempt settings differ from the requested condition')
            row = previous['settings']
        selected.append(row)
    path = root/'plan.json'
    old = json.loads(path.read_text()) if path.exists() else []
    if path.exists() and not resume and old != selected:
        raise ValueError('This output root contains a different plan; choose a fresh --out')
    combined = {key(row): row for row in old} if resume else {}
    for row in selected:
        previous = combined.get(key(row))
        if previous and settings(previous) != settings(row):
            raise ValueError('This output root contains a different plan; choose a fresh --out')
        combined[key(row)] = row
    write(path, list(combined.values()))
    return selected


def save_index(root, study, records):
    root = Path(root)
    path = root/'index.json'
    old = json.loads(path.read_text()).get('runs', []) if path.exists() else []
    combined = {key(row): row for row in old}
    saved = retained(root)
    for record in records:
        previous = saved.get(key(record))
        if previous:
            record = {**previous['record'], **record, 'retained_attempt': True}
            if 'registration' in previous['record']:
                record['registration'] = previous['record']['registration']
        combined[key(record)] = record
    write(path, {'study': study, 'runs': list(combined.values())})
