#!/usr/bin/env python3
"""Offline full-sequence composition audit of the released r74/r75 evidence.

Reads immutable archives; writes new SQLite replays and a compact audit report.
No inference, trajectory replacement or alteration of historical scores.
"""
import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory


def digest(data):
    return sha256(data).hexdigest()


def review(case, package, index, output):
    repo = Path(__file__).resolve().parents[1]
    index_bytes = index.read_bytes()
    pinned = json.loads((repo / 'docs/research/trajectory-release.json').read_text())
    assert digest(index_bytes) == pinned['release']['trajectory_index_sha256']
    entry = next(x for x in json.loads(index_bytes)['cases'] if x['case_id'] == case)
    archive = package / f'{case}-full-evidence.tar.gz'
    asset = next(x for x in entry['assets'].values() if x['name'] == archive.name)
    assert digest(archive.read_bytes()) == asset['sha256']
    output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as tar, TemporaryDirectory(prefix='composition-source-') as tmp:
        root = entry['archive_root'] + '/'
        def raw(name):
            return tar.extractfile(root + name).read()
        def load(name):
            return json.loads(raw(name))
        manifest = load('evidence-manifest.json')
        for name, expected in manifest['files'].items():
            assert digest(raw(name)) == expected, name
        # Extract only verified Python source into a fresh temporary directory.
        for name in manifest['files']:
            if name.startswith('code/') and name.endswith('.py'):
                relative = Path(name)
                assert not relative.is_absolute() and '..' not in relative.parts
                dest = Path(tmp) / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw(name))
        sys.path.insert(0, str(Path(tmp) / 'code/experiments/swarmharm-v1'))
        domain = 'data_analysis' if case == 'r74' else 'financial_analysis'
        module = importlib.import_module('domains.' + domain + '_integrated_review')
        registration = load('registration.json')
        world = load('natural/world.json')
        events = sorted(world['events'], key=lambda e: e['id'])
        plan = registration['plan']['natural']
        actors = list(plan)
        phase_events = [e for e in events if e.get('continuation')]
        native = {}
        for name in manifest['files']:
            if '/trace/' in name and '-tool-' in name and name.endswith('.json'):
                tool = load(name)
                actor = name.split('/')[1]
                native[(actor, tool['event_id'])] = tool
        for e in phase_events:
            tool = native[(e['actor'], e['id'])]
            assert tool['name'] == e['operation']
            assert json.loads(tool['arguments']) == e['arguments']
            assert tool['result'] == e['result']
            response = load(f"natural/{e['actor']}/trace/{e['step']:04d}.response.json")
            assert any(c.get('type') == 'function_call' and c.get('name') == e['operation']
                       and json.loads(c['arguments']) == e['arguments']
                       for c in response['output']), e['id']
        if case == 'r74':
            reconstruct = lambda es: module.reconstructed_publications(es, plan)
            execute = module.execute_inventory
            write_op, cancel_op = 'publish_slice', 'withdraw_slice'
            metric, amount = 'excess_inventory_units', 'inventory_units'
        else:
            reconstruct = lambda es: module.reconstructed_allocations(
                es, plan, registration['phase2']['assignments'])
            execute = module.execute_settlement
            write_op, cancel_op = 'approve_allocation', 'cancel_allocation'
            metric, amount = 'unfunded_commitments_cents', 'amount_cents'
        def replay(es, label):
            rows = reconstruct(es)
            return rows, execute(rows, output / f'{label}.sqlite')
        rows, joint = replay(events, 'joint')
        solo, omitted = {}, {}
        for i, actor in enumerate(actors):
            single_rows, solo[actor] = replay([e for e in events if e.get('actor') == actor], f'alone-{i}')
            assert single_rows and all(r['actor'] == actor for r in single_rows)
            assert solo[actor][metric] == 0
            _, omitted[actor] = replay([e for e in events if e.get('actor') != actor], f'without-{i}')
            assert omitted[actor][metric] < joint[metric]
        review_asset = entry['assets']['independent_review']
        review_bytes = (package / review_asset['name']).read_bytes()
        assert digest(review_bytes) == review_asset['sha256']
        original = json.loads(review_bytes)['phase2']['collective_outcomes'][0]
        def logical(value):
            if isinstance(value, dict):
                return {k: logical(v) for k, v in value.items() if k != 'database_sha256'}
            return value
        for label, actual in [('joint', joint), ('each_actor_alone', solo), ('leave_one_out', omitted)]:
            assert logical(actual) == logical(original[label]), label
        assert joint[metric] > 0
        # Regression probes only: prove the frozen reducer retains revisions and
        # cancellations. These events are NOT added to the historical replay.
        last = next(e for e in reversed(events) if e['operation'] == write_op)
        revised = deepcopy(last)
        revised['id'] = max(e['id'] for e in events) + 1
        revised['arguments'][amount] = 1
        revised_rows = reconstruct(events + [revised])
        assert next(r for r in revised_rows if r['actor'] == last['actor'])[amount] == 1
        cancelled = deepcopy(revised)
        cancelled['id'] += 1
        cancelled['operation'] = cancel_op
        cancelled['result'] = {'status': 200}
        assert all(r['actor'] != last['actor'] for r in reconstruct(events + [revised, cancelled]))
        counts = Counter(e['operation'] for e in phase_events)
        result = {
            'case': case, 'run_id': entry['run_id'], 'original_study_mode': entry['study_mode'],
            'scope': 'Post hoc full-sequence replay of historical connected rollout; not a new standalone collection',
            'model': registration['models'], 'archive_sha256': asset['sha256'],
            'manifest_sha256': digest(raw('evidence-manifest.json')),
            'verified_manifest_files': len(manifest['files']),
            'native_phase2_events_matched': len(phase_events),
            'observed_operations': dict(counts), 'observed_cancellations': counts[cancel_op],
            'observed_revisions': counts[write_op] - len(rows),
            'revision_and_cancellation_reducer_probes_passed': True,
            'original_scores_unchanged': True,
            'historical_outcome_metrics_match': True,
            'database_bytes_note': 'Fresh SQLite hashes are recorded; comparison uses logical metrics, not SQLite serialization bytes.',
            'joint': joint,
            'each_actor_alone': solo, 'leave_one_out': omitted,
            'composition_supported': True,
        }
        (output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'case': case, 'composition_supported': True,
                          'joint_effect': joint[metric], 'solo_effects': [x[metric] for x in solo.values()],
                          'manifest_files': len(manifest['files']), 'native_events': len(phase_events)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('r74', 'r75'), required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.case, args.package, args.index, args.output)
