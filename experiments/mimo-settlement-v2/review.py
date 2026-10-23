"""Summarize frozen trial evidence and package it for Harbor without altering raw records."""
import argparse
import hashlib
import json
import shutil
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from harbor.models.job.result import JobResult, JobStats
from harbor.models.job.config import JobConfig
from harbor.models.trial.result import TrialResult
from harbor.models.trajectories import Trajectory

def read(path): return json.loads(path.read_text())
def write(path, value): path.write_text(json.dumps(value, indent=2) + '\n')
def rows(values): return Counter(json.dumps(v, sort_keys=True) for v in values)

def review(root):
    assert read(root / 'completion.json')['status'] == 'completed'
    trial = root / 'trials/settled-disbursement-v2'; agent = trial / 'agent'
    before = read(agent / 'initial-state.json'); after = read(agent / 'final-state.json')
    changes = {}
    for db in before['databases'].keys() | after['databases'].keys():
        initial = before['databases'].get(db, {}); final = after['databases'].get(db, {})
        for table in initial.keys() | final.keys():
            old, new = rows(initial.get(table, [])), rows(final.get(table, []))
            if old != new or table not in initial or table not in final:
                changes[db + ':' + table] = {'removed_rows': sum((old - new).values()), 'added_rows': sum((new - old).values()),
                                            'table_created': table not in initial, 'table_dropped': table not in final}
    native = sorted((agent / 'trace').glob('*.response.json'))
    calls = read(agent / 'events.json') if (agent / 'events.json').exists() else []
    final = read(agent / 'final.json')
    classifiers = [read(p) for p in agent.glob('classifier-*.json')]
    outcome = read(trial / 'verifier/business-outcome.json')
    result = {'model': read(root / 'started.json')['model'],
              'preflight': read(root / 'preflight/passed.json'),
              'subject_requests': len(native), 'tool_calls': len(calls),
              'elapsed_seconds': final['elapsed_seconds'],
              'native_models': sorted({read(p)['model'] for p in native}),
              'provider_error_files': [str(p.relative_to(root)) for p in root.rglob('*.error.json')],
              'classification_statuses': dict(Counter(v['status'] for v in classifiers)),
              'business_write_calls': [{'step': e['step'], 'name': e['name'], 'arguments': e['arguments'], 'reply': e['reply']}
                                      for e in calls if 'authorize_recommended_payment' in e['name'] or 'create_certificate_version' in e['name']],
              'tool_error_calls': [{'step': e['step'], 'name': e['name']} for e in calls
                                   if e['reply'].get('result', {}).get('isError') or e['reply'].get('error')
                                   or e['reply'].get('exit_code', 0) != 0],
              'business_outcome': outcome, 'database_changes': changes,
              'modified_or_removed_source_files': [p for p, h in before['files'].items() if after['files'].get(p) != h],
              'new_files': sorted(set(after['files']) - set(before['files'])),
              'final_answer': final['text'],
              'scope': 'Single source-derived payment task with contained synthetic cash settlement; no peer-propagation claim.'}
    write(root / 'independent-review.json', result)
    # Exact verifier alias for the frozen generic ATIF exporter's evidence link.
    shutil.copy2(trial / 'verifier/business-outcome.json', trial / 'verifier/business-evidence.json')
    return result

def package(root, destination):
    assert not destination.exists()
    assert read(root / 'atif-validation.json')['trials'][0]['native_continuity_passed']
    trial = root / 'trials/settled-disbursement-v2'
    Trajectory.model_validate_json((trial / 'agent/trajectory.json').read_text())
    result = TrialResult.model_validate_json((trial / 'result.json').read_text())
    destination.mkdir(parents=True); shutil.copytree(trial, destination / trial.name)
    job = JobResult(id=uuid.uuid5(uuid.NAMESPACE_URL, str(root.resolve())),
                    started_at=datetime.fromtimestamp(read(root / 'started.json')['at'], timezone.utc),
                    finished_at=datetime.fromtimestamp(read(root / 'completion.json')['at'], timezone.utc),
                    n_total_trials=1, stats=JobStats.from_trial_results([result], n_total_trials=1), trial_results=[result])
    (destination / 'result.json').write_text(job.model_dump_json(indent=2) + '\n')
    cfg = JobConfig.model_validate({'job_name': destination.name, 'jobs_dir': str(destination.parent),
                                   'n_concurrent_trials': 1, 'retry': {'max_retries': 0},
                                   'agents': [dict(result.config.agent.model_dump(mode='json'), name=result.agent_info.name)],
                                   'tasks': [result.config.task.model_dump(mode='json')],
                                   'environment': result.config.environment.model_dump(mode='json')})
    (destination / 'config.json').write_text(cfg.model_dump_json(indent=2, exclude_unset=True) + '\n')
    evidence = destination / 'study'; evidence.mkdir()
    for name in ['started.json', 'completion.json', 'independent-review.json', 'atif-validation.json']:
        shutil.copy2(root / name, evidence / name)
    shutil.copytree(root / 'preflight', evidence / 'preflight')
    write(destination / 'campaign.json', {
        'format': 'Harbor JobResult aggregation over one actual Harbor Trial',
        'orchestration': 'Single independent task; no campaign sharing or peer sequence',
        'config_origin': 'Viewer metadata derived from actual trial configuration',
        'raw_source': str(root.resolve()),
        'source_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in trial.rglob('*') if p.is_file()}})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('root', type=Path)
    parser.add_argument('--package', type=Path); args = parser.parse_args()
    if args.package: package(args.root, args.package)
    else:
        result = review(args.root)
        print(json.dumps({k: v for k, v in result.items() if k != 'final_answer'}, indent=2))
