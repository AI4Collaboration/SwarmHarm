"""Export completed source evidence. No model calls or automatic intent labels."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil


def load(p):
    return json.loads(p.read_text())


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def digest(p):
    return sha256(p.read_bytes()).hexdigest()


def summarize(root, destination):
    assert not destination.exists(), 'Do not overwrite a published evidence export'
    model = root / 'gpt-6.1-sol'
    reg = load(model / 'registration.json')
    independent = load(model / 'independent-review.json')
    assert load(root / 'completion.json')['models']['gpt-6.1-sol'] == 'reviewed'
    assert independent['passed'], 'Independent replay must pass first'
    assert load(model / 'gate.json')['passed']
    policy = load(model / 'policy-exposure.json')['records']
    handoff = load(model / 'handoff-evidence.json')['worlds']
    workers = []
    for cell in reg['cells']:
        folder = model / cell['id']
        audit = load(folder / 'world.json')
        results = {a['id']: a for a in load(folder / 'results.json')}
        for actor, spec in cell['plan'].items():
            state = audit['state']['actors'][actor]
            submission = state.get('submission') or {}
            events = [e for e in audit['events'] if e['actor_id'] == actor]
            effects = [e for e in events if e['accepted'] and e.get('protected_source_read')]
            peer_reads = [e for e in events if e['accepted'] and e.get('peer_authored_text_read')]
            case = {'world': cell['id'], 'actor': actor, **spec,
                'result': results[actor], 'submission': submission,
                'initial_input': load(folder / actor / 'initial-input.json'),
                'final_answer': (folder / actor / 'final.txt').read_text(),
                'source_read_events': effects, 'peer_body_read_events': peer_reads,
                'publication_events': [e for e in events if e['accepted'] and e.get('shared_text_write')],
                'cache_policy_exposure': [p for p in policy if p['actor'] == actor],
                'world_sha256': digest(folder / 'world.json'),
                'interpretation': 'Source access, content use and method adoption require separate semantic review.'}
            save(destination / 'cases' / (actor + '.json'), case)
            workers.append({'world': cell['id'], 'actor': actor, **spec,
                'status': results[actor]['status'], 'responses': results[actor]['steps'],
                'tools': results[actor]['tools'],
                'unauthorized_read_events': [e['event_id'] for e in effects],
                'peer_body_read_events': [e['event_id'] for e in peer_reads],
                'truth': submission.get('truth'),
                'source_authorized': submission.get('evidence_authorized')})
    reviews = load(model / 'response-review.json')
    summary = {'model': reg['model'], 'reasoning': reg['reasoning'],
        'independent_worlds': len(reg['cells']), 'experimental_workers': len(workers),
        'calibration_workers': len(reg['calibration']['plan']),
        'provider_response_statuses': dict(Counter(r['status'] for r in reviews)),
        'response_counts_by_phase': {phase: len(list((model / name).rglob('*.response.json')))
            for phase, name in [('preflight', 'preflight'), ('calibration', 'calibration')]
            + [('natural', cell['id']) for cell in reg['cells']]},
        'provider_error_files': [str(p.relative_to(model)) for p in model.rglob('*.error.json')],
        'unauthorized_readers': sum(bool(w['unauthorized_read_events']) for w in workers),
        'peer_artifact_readers': sum(bool(w['peer_body_read_events']) for w in workers),
        'workers': workers, 'handoff_counts': [w['counts'] for w in handoff],
        'independent_review_passed': independent['passed'],
        'output_quality': load(model / 'output-quality.json')['passed'],
        'method_adoption': 'Requires manual review of actual method content, prior request exposure and different-object use.',
        'limits': reg['comparison_limit'], 'source_output': str(root.resolve())}
    save(destination / 'summary.json', summary)
    for name in ('registration.json', 'registration-seal.json', 'gate.json', 'independent-review.json',
                 'policy-exposure.json', 'handoff-evidence.json', 'output-quality.json', 'cleanup-summary.json',
                 'completion.json', 'initial-input-audit.json', 'controls.json'):
        shutil.copyfile(model / name, destination / name)
    for name in ('study.json', 'completion.json'):
        shutil.copyfile(root / name, destination / ('study-' + name))
    shutil.copyfile(model / 'code/experiments/sol-benign-elicitation-v1/run.py', destination / 'frozen-collector.py')
    source = Path(__file__).resolve()
    shutil.copyfile(source, destination / 'export-code.py')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    a = p.parse_args()
    summarize(a.output.resolve(), a.destination.resolve())
