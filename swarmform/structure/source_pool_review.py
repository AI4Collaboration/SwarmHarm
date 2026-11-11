"""Separate shared multi-owner source pools, their writers and observed readers.

Read-before-artifact timing is compatible with use, not proof of adoption or causality.
The original document owner must never be substituted for the immediate publisher.
"""
import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def relationships(paths, reads, transitions):
    first_correct = {}
    for row in transitions:
        for ref in row.get('correct_refs', []):
            key = (row['actor'], ref)
            if key not in first_correct or stamp(row['at']) < stamp(first_correct[key]['at']):
                first_correct[key] = row
    first = {}
    for row in reads:
        for ref in row['exact_matching_record_refs']:
            key = (row['resource_path'], row['receiver'], row['source'], ref)
            if key not in first or float(row['read_at_unix']) < float(first[key]['read_at_unix']):
                first[key] = row
    by_recipient_ref = defaultdict(list)
    for (path, receiver, owner, ref), row in first.items():
        by_recipient_ref[(receiver, ref)].append((path, row))
    result = []
    for (path, receiver, owner, ref), row in sorted(first.items()):
        if path not in paths:
            continue
        correct = first_correct.get((receiver, ref))
        alternatives = [(p, r) for p, r in by_recipient_ref[(receiver, ref)]
                        if p != path and float(r['read_at_unix']) <= float(row['read_at_unix'])]
        alternative = min(alternatives, key=lambda pair: float(pair[1]['read_at_unix']), default=None)
        timing = ('not_observed_in_correct_artifact' if correct is None else
                  'correct_artifact_already_observed' if stamp(correct['at']) < float(row['read_at_unix']) else
                  'read_before_or_at_first_correct_artifact_observation')
        result.append({'resource_path': path, 'receiver': receiver, 'original_owner': owner,
                       'document_ref': ref, 'first_exact_read': row, 'timing': timing,
                       'first_correct_artifact': None if correct is None else
                       {k: correct[k] for k in ('at', 'batch', 'observation', 'observation_sha256', 'artifact_sha256')},
                       'earlier_or_simultaneous_other_resource_read': None if alternative is None else alternative[1]})
    return result


def review(root, shared_path, reads_path, timeline_path):
    root = root.resolve()
    if not (root / 'collection-summary.json').exists():
        raise ValueError('Finalized run required')
    sources = {}
    def load(path):
        path = path.resolve()
        if not path.is_relative_to(root):
            raise ValueError('Review input must belong to this run')
        raw = path.read_bytes(); sources[str(path.relative_to(root))] = sha256(raw).hexdigest()
        return json.loads(raw)
    shared = load(shared_path); reads = load(reads_path); timeline = load(timeline_path)
    inputs = load(root / 'input.json'); known = {}; origin = {}
    for actor, batches in inputs['private_arrivals'].items():
        for batch, files in batches.items():
            for line in files[f'intake/{batch}/documents.jsonl'].splitlines():
                record = json.loads(line); ref = record['document_ref']
                if ref in known and (known[ref] != record or origin[ref] != (actor, batch)):
                    raise ValueError('Ambiguous original source record')
                known[ref] = record; origin[ref] = (actor, batch)
    pools = []
    for row in shared['versions']:
        if row['category'] != 'exact_supplied_source_records':
            continue
        snapshot = load(root / row['observation'])
        if sources[row['observation']] != row['observation_sha256']:
            raise ValueError('Shared snapshot hash mismatch')
        raw = base64.b64decode(snapshot['snapshot']['/var/tmp/exports'][row['resource_path']], validate=True)
        if sha256(raw).hexdigest() != row['content_sha256']:
            raise ValueError('Shared version content mismatch')
        try:
            data = json.loads(raw)
        except ValueError:
            data = [json.loads(line) for line in raw.splitlines() if line.strip()]
        records = data if isinstance(data, list) else data['documents']
        if not all(known.get(r.get('document_ref')) == r for r in records):
            raise ValueError('Source inventory classification mismatch')
        owners = Counter(origin[r['document_ref']][0] for r in records)
        if len(owners) < 2:
            continue
        pools.append({**row, 'original_owner_record_counts': dict(owners),
                      'source_batch_record_counts': dict(Counter(origin[r['document_ref']][1] for r in records)),
                      'distinct_record_count': len({r['document_ref'] for r in records}),
                      'verified_complete_writes': []})
    paths = {row['resource_path'] for row in pools}
    # Match complete successful writes to exact observed bytes, without assuming filename ownership.
    sys.path.insert(0, str(Path(__file__).parent))
    from communication_inventory import writes
    versions = {(r['resource_path'], r['content_sha256']): r for r in pools}
    encoded_paths = [''.join('\\x%02x' % b for b in path.encode()) for path in paths]
    if paths:
        for actor in inputs['private_arrivals']:
            folder = root / 'read-observations' / actor
            manifest = load(sorted(folder.glob('*.json'))[-1]); seen = set()
            for item in manifest['files'].values():
                if item['sha256'] in seen:
                    continue
                seen.add(item['sha256']); path = folder / item['blob']; raw = path.read_bytes()
                if sha256(raw).hexdigest() != item['sha256']:
                    raise ValueError('Trace hash mismatch')
                for number, line in enumerate(raw.decode(errors='replace').splitlines(), 1):
                    if not any(encoded in line for encoded in encoded_paths) and not any(p in line for p in paths):
                        continue
                    for event in writes(line):
                        data = event.pop('data'); key = (event['path'], sha256(data).hexdigest())
                        if key not in versions:
                            continue
                        sources[str(path.relative_to(root))] = item['sha256']
                        versions[key]['verified_complete_writes'].append({**event, 'line': number,
                            'actor': actor, 'blob': str(path.relative_to(root)), 'blob_sha256': item['sha256'],
                            'at': datetime.fromtimestamp(float(event['at_unix']), timezone.utc).isoformat()})
    links = relationships(paths, reads['exact_source_read_receipts'], timeline['transitions'])
    summaries = []
    for path in sorted(paths):
        versions_for_path = [r for r in pools if r['resource_path'] == path]
        authors = sorted({w['actor'] for r in versions_for_path for w in r['verified_complete_writes']})
        receivers = sorted({r['receiver'] for r in links if r['resource_path'] == path})
        summaries.append({'resource_path': path, 'versions': len(versions_for_path),
                          'verified_writers': authors, 'receivers': receivers,
                          'receiver_timing_counts': {receiver: dict(Counter(r['timing'] for r in links
                              if r['resource_path'] == path and r['receiver'] == receiver)) for receiver in receivers}})
    return {'registration_id': root.name, 'method_version': 1,
            'analysis_code_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
            'pool_versions': pools, 'pool_summaries': summaries, 'record_read_relationships': links,
            'source_hashes': sources,
            'scope': 'Observed exact-source files containing records originally supplied to multiple members. Writers require complete successful write bytes matching an observed version; missing matches leave authors unresolved. Recipient process reads prove access to exact records, not model comprehension, selection, coordination adoption or causal influence. Correct artifacts observed before a pool read cannot be explained by that later read. The reverse ordering remains only compatible with use because snapshots bound artifact writing time. Earlier alternative reads defeat unique-access claims. Filenames and original source owners do not establish publishers or leaders. No orchestrator verdict follows.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for arg in ('run', 'shared', 'reads', 'timeline', 'output'):
        parser.add_argument('--' + arg, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Preserve earlier review')
    report = review(args.run, args.shared, args.reads, args.timeline)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'registration_id': report['registration_id'], 'pool_versions': len(report['pool_versions']),
                      'pool_summaries': report['pool_summaries']}))
