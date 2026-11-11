"""Reproducible observer-only 3x3 reannotation of immutable semantic evidence.

Labels are explicit human/operator annotations, never keyword classifications.
Passive windows locate evidence; they do not impute persistence between events.
"""
import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

ROWS = ('no_leader', 'multi_leader', 'single_leader')
COLS = ('no_information_flow', 'one_way', 'two_way')


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def seconds(value, activation):
    return (datetime.fromisoformat(value.replace('Z', '+00:00')) -
            datetime.fromisoformat(activation.replace('Z', '+00:00'))).total_seconds()


def evidence_hashes(root, value):
    """Recheck every cited immutable file; do not modify historical review files."""
    verified = {}
    def walk(item):
        if isinstance(item, dict):
            for name, hash_name in (('path', 'sha256'), ('path', 'file_sha256'), ('blob', 'blob_sha256')):
                if not isinstance(item.get(name), str) or hash_name not in item:
                    continue
                path = root/item[name]
                if item[name].startswith('/var/tmp/exports/'):
                    path = root/'publication-updates/blobs'/item[hash_name]
                path = path.resolve()
                if not path.is_relative_to(root.resolve()):
                    raise ValueError('Evidence path escaped its immutable run')
                key = str(path.relative_to(root.resolve()))
                if key not in verified:
                    verified[key] = digest(path)
                if verified[key] != item[hash_name]:
                    raise ValueError('Evidence changed: '+str(path))
            if 'line_sha256' in item:
                line=(root/item['path']).read_text().splitlines()[item['line']-1]
                if sha256(line.encode()).hexdigest() != item['line_sha256']:
                    raise ValueError('Cited native line changed')
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return verified


def delegation_chain(edges):
    """A connected same-task request/execution/return chain, not a citation path."""
    accepted = []
    for a in edges:
        for b in edges:
            if (a['recipient'] != b['sender'] or a['sender'] == b['recipient'] or
                    b.get('parent_task') != a.get('task') or not a.get('task')):
                continue
            keys = ('received_at', 'executed_at', 'returned_at', 'return_received_at')
            if not all(e.get(k) is not None for e in (a, b) for k in keys):
                continue
            if not all(e['sent_at'] <= e['received_at'] <= e['executed_at'] <= e['returned_at'] <= e['return_received_at'] for e in (a,b)):
                continue
            if not (a['sent_at'] <= a['received_at'] <= b['sent_at'] <= b['received_at']
                    <= b['executed_at'] <= b['returned_at'] <= b['return_received_at']
                    <= a['returned_at'] <= a['return_received_at']):
                continue
            if not b.get('result_used_in_parent'):
                continue
            accepted.append([a['sender'], a['recipient'], b['recipient']])
    return accepted


def compile_run(root, source, labels):
    review_path = root/source['review']
    if digest(review_path) != source['review_sha256']:
        raise ValueError('Historical review changed')
    for name, expected in source.get('required_files', {}).items():
        if digest(root/name) != expected:
            raise ValueError('Original run metadata changed: '+name)
    review = read(review_path)
    hashes = evidence_hashes(root, review['events'])
    activation = read(root/'activation.json')['at']
    completion = read(root/'completion.json')
    duration = review.get('duration_seconds')
    if duration is None:
        duration = seconds(completion['at'], activation)
    close_duration = duration
    failure = completion.get('failure') or {}
    if failure.get('at'):
        duration = min(duration, seconds(failure['at'], activation))
    terminal = 'natural_record_end' if completion.get('reason') == 'quiescence' else 'externally_censored'
    events = []
    if set(labels['events']) != {e['id'] for e in review['events']}:
        raise ValueError('Every retained semantic event needs an explicit label')
    for original in review['events']:
        label = labels['events'][original['id']]
        row, col = label['row'], label['flow']
        if row is not None and row not in ROWS or col is not None and col not in COLS:
            raise ValueError('Unknown taxonomy coordinate')
        hubs = label.get('hubs', [])
        if row == 'single_leader' and len(hubs) != 1 or row == 'multi_leader' and len(hubs) < 2:
            raise ValueError('Leadership count lacks named functional hubs')
        if not set(hubs) <= set(original['members']):
            raise ValueError('Hub is not in the cited subgroup')
        if row == 'no_leader' and hubs:
            raise ValueError('Flat episode has hubs')
        start = seconds(original['first_at'], activation)
        end = seconds(original['last_at'], activation)
        events.append({**label, 'id': original['id'], 'title': original['title'],
            'start_seconds': start, 'end_seconds': end,
            'evidence_complete_before_cutoff': end <= duration, 'members': original['members'],
            'source_kind': original.get('kind'), 'interpretation': original['interpretation'],
            'cell': row+'/'+col if row and col else None,
            'source_pointer': '/events/'+str(review['events'].index(original)),
            'classification_scope': 'named episode and subgroup; no whole-cohort or exclusive-authority inference'})
    windows = []
    start = 0
    while start < duration:
        end = min(start+300, duration)
        active = [e for e in events if e['start_seconds'] < end and e['end_seconds'] >= start]
        completed = [e for e in events if start <= e['end_seconds'] < end or
                     end == duration and e['end_seconds'] == end]
        windows.append({'start_seconds': start, 'end_seconds': end,
            'overlapping_episodes': [e['id'] for e in active],
            'completed_evidence': [e['id'] for e in completed],
            'supported_episode_cells': sorted({e['cell'] for e in completed if e['cell']}),
            'unresolved_episodes': [e['id'] for e in completed if not e['cell']],
            'cohort_state': 'not_imputed',
            'boundary': terminal if end == duration else 'passive_window',
            'comparison_scope': ('common_first_30_minutes' if end <= 1800 else 'unmatched_extension')
                if 'async-v2' in review['registration_id'] else 'separate_historical_version'})
        start = end
    return {'registration_id': review['registration_id'], 'run_path': str(root),
        'source_review': source, 'condition_interpretation': labels['condition_interpretation'],
        'activation_at': activation, 'duration_seconds': duration,
        'close_seconds': close_duration, 'terminal': terminal,
        'events': events, 'windows': windows, 'temporal_findings': labels['temporal_findings'],
        'delegation_review': labels['delegation_review'],
        'previous_orchestrator_verdict': review['findings'].get('orchestrator_established',
            review['findings'].get('strict_sustained_orchestrator_certified')),
        'previous_findings': review['findings'], 'verified_source_files': hashes,
        'native_export_coverage': {a: (root/'natural'/a/'codex/session.jsonl').exists()
            for a in sorted(read(root/'registration.json')['plan']['natural'])},
        'limitations': ['Retrospective operator annotation, not an independent blinded replication.',
            'One-way denotes a verified directed episode with no verified return in that episode; not absence of all reverse flow.',
            'Windows record evidence completion, not exact onset, persistence, disappearance or causality.',
            'Unknown is outside the grid. No peer receipt is not inferred from no JSON messages or peer exit.',
            'An integration hub is structural evidence; it does not alone certify an orchestrator.',
            'Original scores, registrations and runtime failures remain unchanged.']}


def build(manifest_path, annotation_path, output):
    manifest, annotations = read(manifest_path), read(annotation_path)
    runs = []
    for source in manifest['runs']:
        runs.append(compile_run(Path(source['root']), source, annotations['runs'][source['identifier']]))
    result = {'schema_version': 1, 'taxonomy': {'rows': ROWS, 'columns': COLS,
        'readme_sha256': manifest['readme_sha256'], 'aggregation_counts_as_structure': True},
        'annotation_sha256': digest(annotation_path), 'source_manifest_sha256': digest(manifest_path),
        'research_rollouts': 0, 'window_seconds': 300, 'runs': runs}
    if output.exists():
        raise FileExistsError('Use a new derived review version')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.manifest, args.annotations, args.output)
    print(json.dumps({'runs': len(result['runs']), 'output': str(args.output), 'research_rollouts': 0}))
