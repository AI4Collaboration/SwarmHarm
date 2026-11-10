"""Retained common-problem artifacts and native evidence, with no semantic verdict."""
import argparse
import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import communication_inventory


def read(path):
    return json.loads(path.read_text())


def shared_versions(root):
    versions = {}
    snapshot_count = 0
    for path in sorted(root.glob('natural/*/observations/*.json')):
        raw = path.read_bytes()
        record = json.loads(raw)
        snapshot_count += 1
        observer = path.parts[-3]
        for resource, encoded in record['snapshot'].get('/var/tmp/exports', {}).items():
            content = base64.b64decode(encoded, validate=True)
            key = resource, sha256(content).hexdigest()
            reference = {'at': record['at'], 'path': str(path.relative_to(root)),
                         'sha256': sha256(raw).hexdigest(), 'observer': observer}
            if key not in versions:
                try:
                    text = content.decode('utf-8')
                except UnicodeDecodeError:
                    text = None
                versions[key] = {'resource': resource, 'content_sha256': key[1],
                    'bytes': len(content), 'text': text, 'first_observation': reference,
                    'last_observation': reference, 'observers': set(), 'observation_count': 0}
            row = versions[key]
            row['observers'].add(observer)
            row['observation_count'] += 1
            if reference['at'] < row['first_observation']['at']:
                row['first_observation'] = reference
            if reference['at'] > row['last_observation']['at']:
                row['last_observation'] = reference
    result = sorted(versions.values(), key=lambda row: (row['first_observation']['at'], row['resource']))
    for index, row in enumerate(result, 1):
        row['id'] = f'v{index:05d}'
        row['observers'] = sorted(row['observers'])
    return {'snapshot_count': snapshot_count, 'versions': result,
            'scope': 'All retained shared-file versions, not author attribution, readership or adoption. Snapshot times bound visibility and are not exact write times.'}


def usage_review(root, completion):
    actors = {}
    sources = {}
    for actor, state in completion['actors'].items():
        seen = {}
        row = dict(responses=0, input_tokens=0, cached_input_tokens=0, uncached_input_tokens=0, output_tokens=0)
        for path in sorted((root/'natural'/actor/'trace').glob('*.response.json')):
            raw = path.read_bytes()
            response = json.loads(raw)
            usage = response.get('usage')
            if not usage:
                continue
            if response['id'] in seen:
                if seen[response['id']] != usage:
                    raise ValueError('Inconsistent usage for one native response')
                continue
            seen[response['id']] = usage
            row['responses'] += 1
            row['input_tokens'] += usage['input_tokens']
            row['output_tokens'] += usage['output_tokens']
            cached = usage.get('input_tokens_details', {}).get('cached_tokens', 0)
            row['cached_input_tokens'] += cached
            row['uncached_input_tokens'] += usage['input_tokens'] - cached
            sources[str(path.relative_to(root))] = sha256(raw).hexdigest()
        row['reconciles'] = (row['input_tokens'] + row['output_tokens'] == state.get('observed_tokens', 0)
                             and row['responses'] == state.get('observed_model_responses', 0))
        actors[actor] = row
    fields = ('responses', 'input_tokens', 'cached_input_tokens', 'uncached_input_tokens', 'output_tokens')
    return {'actors': actors, 'totals': {key: sum(row[key] for row in actors.values()) for key in fields},
            'all_reconcile': all(row['reconciles'] for row in actors.values()), 'source_hashes': sources,
            'scope': 'Observed native response groups only, not billed cost; opaque provider retries are excluded.'}


def review(root, folder):
    root = root.resolve()
    if not (root/'collection-summary.json').exists():
        raise ValueError('Finalized runs only')
    registration = read(root/'registration.json')
    if registration.get('workload') != 'navier-stokes-theory':
        raise ValueError('Expected the registered common theory problem')
    completion = read(root/'completion.json')
    if folder.exists():
        raise FileExistsError('Preserve previous review versions')
    folder.mkdir(parents=True)
    artifacts = shared_versions(root)
    usage = usage_review(root, completion)
    messages = communication_inventory.inventory(root)
    retained = {'shared-versions': artifacts, 'usage': usage, 'communications': messages}
    refs = {}
    for name, value in retained.items():
        path = folder/(name+'.json')
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        refs[str(path.relative_to(root))] = sha256(path.read_bytes()).hexdigest()
    coverage = read(root/'actor-evidence.json')
    summary = {'at': datetime.now(timezone.utc).isoformat(), 'registration_id': registration['identifier'],
        'condition': registration['condition'], 'population': registration['population'],
        'completion_reason': completion['reason'], 'failure': completion.get('failure'),
        'actor_evidence_complete': coverage['actor_evidence_complete'],
        'shared_versions': len(artifacts['versions']), 'recognized_message_writes': len(messages['messages']),
        'actual_native_calls': sum(len(actor['calls']) for actor in messages['native'].values()),
        'observed_usage': usage['totals'], 'usage_reconciled': usage['all_reconcile'],
        'review_files': refs, 'operator_code_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'communication_code_sha256': sha256(Path(communication_inventory.__file__).read_bytes()).hexdigest(),
        'mathematical_review': 'pending', 'structural_review': 'pending',
        'scope': 'Evidence inventory for separate claim-by-claim and structural review. Missing recognized envelopes does not establish no communication. No automatic role, correctness, originality or causal claim.'}
    (folder/'index.json').write_text(json.dumps(summary, indent=2)+'\n')
    return {key: summary[key] for key in ('registration_id', 'completion_reason', 'actor_evidence_complete',
            'shared_versions', 'recognized_message_writes', 'actual_native_calls', 'observed_usage', 'usage_reconciled')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(review(args.run, args.output)))
