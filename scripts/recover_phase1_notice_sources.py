"""Recover omitted notification attribution beside, never inside, frozen rollouts."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'experiments/swarmharm-v1'), str(REPO/'experiments/runtime')]
import run


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def reconstruct(shared, actor, publication):
    # The common case store enumerates records by path. Reproduce its ordinary
    # subscription rule directly from committed writes, without rerunning commands.
    introduced, joined, selected = set(), set(), []
    for path, record in sorted(shared.items()):
        if not path.startswith('/registry/cache/reviews/'):
            continue
        data = base64.b64decode(record['data'], validate=True)
        assert sha256(data).hexdigest() == record['sha256']
        body = json.loads(data)
        if body.get('operation') not in ('source_resolution_diagnostic', 'source_resolution_note'):
            continue
        case = body['review_id']; key = (case, body['operation'])
        first = key not in introduced; introduced.add(key)
        if record['author'] == actor:
            joined.add(case)
        elif first or case in joined:
            selected.append({'path': path, 'sha256': record['sha256'], 'case': case})
    pairs = [(r['path'], r['sha256']) for r in selected]
    revision = sha256(json.dumps([sorted(pairs), publication], separators=(',', ':')).encode()).hexdigest()
    cases = {}
    for row in selected:
        cases.setdefault(row['case'], []).append((row['path'], row['sha256']))
    return {'revision': revision,
            'case_revisions': {k: sha256(json.dumps(v).encode()).hexdigest() for k,v in cases.items()},
            'monitored_case_entries': {k: [{'path': p, 'sha256': h} for p,h in v] for k,v in cases.items()}}


def recover(root):
    load = lambda name: json.loads((root/name).read_text())
    world, registration = load('natural/world.json'), load('registration.json')
    assert registration['cue_condition'] == 'agent_initiated_activity'
    actors = list(world['plan']); shared, states, prefixes = {}, {a:{} for a in actors}, {}
    publication = None
    for count in range(len(world['events'])+1):
        if count:
            event = world['events'][count-1]
            for record in event.get('shared_changes', []):
                if not record['path'].startswith('/registry/cache/reviews/'):
                    continue
                assert record['author'] == event['actor']
                shared[record['path']] = record
            if event['operation'] == 'publish_final_build':
                publication = event['id']
        prefixes[count] = {a: reconstruct(shared, a, publication) for a in actors}
        for actor, state in prefixes[count].items():
            states[actor][state['revision']] = state
    notices = []
    for path in sorted(root.glob('natural/*/trace/*-platform-update.json')):
        actor = path.parent.parent.name; note = json.loads(path.read_text()); monitor = note['shared_monitor']
        after = prefixes[monitor['world_event_count']][actor]
        before = states[actor][monitor['before']['filing_revision']]
        for saved, reconstructed in ((monitor['after'], after), (monitor['before'], before)):
            assert saved['filing_revision'] == reconstructed['revision']
            assert saved['case_revisions'] == reconstructed['case_revisions']
        augmented = []
        for saved, reconstructed in ((monitor['before'], before), (monitor['after'], after)):
            filing = {**saved, 'revision': saved['filing_revision'],
                      'monitored_case_entries': reconstructed['monitored_case_entries']}
            combined = run.combined_activity_signal(filing, {'revision': None, 'relevant_cross_job_records': 0}, False)
            assert {k:v for k,v in combined.items() if k != 'monitored_case_entries'} == saved
            augmented.append(combined)
        from types import SimpleNamespace
        observed = run.monitored_notice(SimpleNamespace(plan=world['plan'], events=world['events'][:monitor['world_event_count']]),
                                       augmented[1], augmented[0])['shared_monitor']
        assert observed['source_records']
        if monitor['source_records']:
            assert monitor['source_records'] == observed['source_records']
        assert run.activity_feedback(augmented[1], augmented[0]) == json.loads(note['input_message']['content'])['status']
        notices.append({'path':str(path.relative_to(root)), 'sha256':digest(path),
                        'actor':actor, 'source_records_were_omitted':not monitor['source_records'],
                        'reconstructed_sources':observed['source_records'],
                        'original_notice_and_result_preserved':True})
    return {'rollout':root.name, 'registration_sha256':digest(root/'registration.json'),
            'terminal_manifest_sha256':digest(root/'evidence-manifest.json'),
            'world_sha256':digest(root/'natural/world.json'),
            'frozen_review_sha256':digest(root/'independent-review.json'),
            'notices':notices, 'model_calls':0,
            'scope':'Supplementary attribution from original events; no replacement notification, score or trajectory.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); evidence=args.evidence_root.resolve(); output=args.output.resolve()
    assert not output.exists(), 'Use a fresh supplementary output directory'
    configs=json.loads((REPO/'docs/research/phase1-input-configs.json').read_text())['configs']
    assert all(not output.is_relative_to(evidence/c['rollout']) for c in configs)
    reports=[recover(evidence/c['rollout']) for c in configs]
    output.mkdir(parents=True)
    for report in reports:
        (output/(report['rollout']+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    result={'inputs':len(reports), 'notices':sum(len(r['notices']) for r in reports),
            'recovered_omissions':sum(n['source_records_were_omitted'] for r in reports for n in r['notices']),
            'original_results_preserved':True, 'model_calls':0,
            'script_sha256':digest(Path(__file__)),
            'files':{p.name:digest(p) for p in output.glob('*.json')}}
    (output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
