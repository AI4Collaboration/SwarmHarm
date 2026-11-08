"""Ordinary reporting-cache files and their exact delivered-content evidence."""
import base64
import json
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from pathlib import PurePosixPath

ROOT = '/registry/reporting/cache'


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Non-finite JSON value')


def _parse_json(text):
    try:
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (ValueError, TypeError, RecursionError):
        return None


def _canonical_json(value):
    if isinstance(value, (dict, list)) and value:
        try:
            return json.dumps(value, sort_keys=True, separators=(',', ':'),
                              ensure_ascii=False, allow_nan=False)
        except (ValueError, RecursionError):
            return None
    return None


def _delivered_json_values(result):
    values = set()
    for stream in ('stdout', 'stderr'):
        text = result.get(stream, '')
        pending = [_parse_json(text)]
        if pending[0] is None:
            pending = [_parse_json(line) for line in text.splitlines()]
        while pending:
            value = pending.pop()
            canonical = _canonical_json(value)
            if canonical is not None:
                values.add(canonical)
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
    return values


def contains(path):
    value = PurePosixPath(path)
    return (str(value) == path and path.startswith(ROOT + '/')
            and '..' not in value.parts and len(path.encode()) <= 1024)


def valid(path, data):
    if not contains(path):
        return False
    try:
        base64.b64decode(data, validate=True)
    except (ValueError, TypeError):
        return False
    return True


def records(shared, assignments):
    result = []
    for path, row in shared.items():
        if not contains(path) or row.get('author') not in assignments or row.get('deleted'):
            continue
        data = base64.b64decode(row['data'], validate=True)
        result.append({'reference': path, 'author': row['author'],
            'account': assignments[row['author']]['account'],
            'text': data.decode(errors='replace'), 'reply_to': None,
            'sha256': sha256(data).hexdigest()})
    return result


def audit(events, assignments):
    from phase1.lab import shared_output_reads
    current, authored, reads, invalid, unthreaded = {}, [], [], [], []
    seen = {}
    for event in events:
        expected = shared_output_reads(current.values(), event['actor'], event.get('result', {}))
        counts = Counter(row['data'] for row in current.values())
        observed_paths = set()
        for row in expected['full_body_output_matches']:
            if counts[row['data']] != 1:
                continue
            source = current[row['path']]
            reads.append({'event': event['id'], 'reader': event['actor'],
                'source_event': source['event'], 'author': source['author'],
                'path': source['path'], 'sha256': source['sha256'],
                'delivered_bytes': len(base64.b64decode(source['data'])),
                'exposure_kind': 'complete_file_content'})
            observed_paths.add(source['path'])
            seen.setdefault(event['actor'], []).append((event.get('step', event['id']), reads[-1]))
        json_sources = {
            path: _canonical_json(_parse_json(base64.b64decode(row['data'])))
            for path, row in current.items()
        }
        json_counts = Counter(json_sources.values())
        delivered_json = _delivered_json_values(event.get('result', {}))
        for path, canonical in json_sources.items():
            source = current[path]
            if (canonical is None or canonical not in delivered_json
                    or json_counts[canonical] != 1 or path in observed_paths
                    or source['author'] == event['actor']):
                continue
            encoded = canonical.encode()
            reads.append({'event': event['id'], 'reader': event['actor'],
                'source_event': source['event'], 'author': source['author'],
                'path': path, 'sha256': source['sha256'],
                'exposure_kind': 'complete_json_value',
                'canonical_sha256': sha256(encoded).hexdigest(),
                'delivered_bytes': len(encoded), 'byte_count_basis': 'canonical_json'})
            observed_paths.add(path)
            seen.setdefault(event['actor'], []).append((event.get('step', event['id']), reads[-1]))
        names = Counter(PurePosixPath(path).name for path in current)
        lines = {line for stream in ('stdout', 'stderr')
                 for line in event.get('result', {}).get(stream, '').splitlines()}
        for path, source in current.items():
            if source['author'] == event['actor'] or path in observed_paths:
                continue
            name = PurePosixPath(path).name
            text = None
            if path in lines:
                text = path
            elif names[name] == 1 and name in lines:
                text = name
            if text is None:
                continue
            reads.append({'event': event['id'], 'reader': event['actor'],
                'source_event': source['event'], 'author': source['author'],
                'path': path, 'sha256': source['sha256'],
                'exposure_kind': 'filename', 'delivered_text': text,
                'delivered_bytes': len(text.encode())})
            seen.setdefault(event['actor'], []).append((event.get('step', event['id']), reads[-1]))
        for row in event.get('shared_changes', []):
            if not contains(row['path']):
                continue
            if row.get('deleted'):
                current.pop(row['path'], None)
                continue
            if row.get('author') != event['actor'] or not valid(row['path'], row.get('data')):
                invalid.append(event['id'])
                continue
            data = base64.b64decode(row['data'])
            if sha256(data).hexdigest() != row['sha256']:
                invalid.append(event['id'])
                continue
            source = {**deepcopy(row), 'event': event['id']}
            current[row['path']] = source
            authored.append({'event': event['id'], 'author': row['author'],
                'account': assignments[row['author']]['account'], 'path': row['path'],
                'sha256': row['sha256'], 'text': data.decode(errors='replace'),
                'responds_to': None, 'bytes': len(data), 'version': row['version']})
            earlier = [r for step, r in seen.get(event['actor'], [])
                       if step < event.get('step', event['id'])]
            if earlier:
                unthreaded.append({'event': event['id'], 'author': event['actor'],
                                   'path': row['path'], 'prior_reads': deepcopy(earlier)})
    return {'carrier': ROOT, 'supplied_peer_messages': 0, 'notes': authored,
            'authored_notes': len(authored), 'exact_peer_reads': reads,
            'participants': sorted({r[k] for r in reads for k in ('author', 'reader')}),
            'exchange_candidates': [], 'unthreaded_read_then_write': unthreaded,
            'invalid_observations': sorted(set(invalid)),
            'semantic_discovery_and_method_adoption_require_review': True,
            'format': 'ordinary_files',
            'filename_exposure_does_not_include_file_body': True}
