"""Private jq reconstruction task reused across the three first-contact interfaces."""
from hashlib import sha256
from pathlib import PurePosixPath

from swarmform import programbench_pilot

KEYS = ('jq-reconstruction',)
OUTPUT_ROOT = '/workspace/output/jq'


def build(key, population):
    if key not in KEYS:
        raise ValueError('Unknown formation benchmark task')
    from swarmform.population import research_actors
    truth = programbench_pilot.specification()
    fixtures = programbench_pilot.FIXTURES
    manual = (fixtures/'programbench-jq-manual.txt').read_text()
    license_text = (fixtures/'programbench-jq-LICENSE.txt').read_text()
    if sha256(manual.encode()).hexdigest()!=truth['manual_sha256'] or sha256(license_text.encode()).hexdigest()!=truth['license_sha256']:
        raise ValueError('Reference documentation changed')
    startup = {a: {'/workspace/jq-manual.txt': manual, '/workspace/jq-LICENSE.txt': license_text}
               for a in research_actors(population)}
    destination = OUTPUT_ROOT
    task = programbench_pilot.TASK.split('Continue useful improvements')[0]
    environment = (
        '/workspace is private working storage. Save runnable ZIP submissions under '
        + destination + '. Python 3 and its standard library are available. '
        'Use Python to run working scripts in /workspace. The reference program '
        'is on a read-only, execute-only mount at /opt/reference/jq. No C/C++ compiler, '
        'third-party Python packages, package downloads or internet are available. '
        'No further inputs will arrive.\n'
    )
    assets = {'reference_program': {name: truth[name] for name in
                                   ('reference_binary_sha256', 'reference_binary_bytes',
                                    'reference_architecture')}}
    task = task.replace(programbench_pilot.OUTPUT_ROOT, destination)
    for files in startup.values():
        files.pop('/workspace/research-session.md', None)
        files['/workspace/task.md'] = task
        files['/workspace/environment.txt'] = environment
    metadata = {
        'task_version': 'formation-benchmarks-v1', 'domain': 'Engineering',
        'task_class': 'possible', 'output_paths': [destination], 'assets': assets,
        'reference_questions': {}, 'difficulty_status': 'uncalibrated_for_current_model_and_budget',
        'source_task': programbench_pilot.KEY,
        'evaluation_scope': 'Fixed 61-item development subset, native ARM adaptation',
    }
    return startup, truth, metadata


def witness(key, startup, truth):
    expected, expected_truth, metadata = build(key, len(startup))
    checks = {
        'task_identity': startup == expected, 'truth_identity': truth == expected_truth,
        'reference_subset': truth.get('reference_gate_passed_items') == 61
                            and len(truth.get('selected_tests', [])) == 61,
    }
    return {'passed': all(checks.values()), 'model_calls': 0, 'checks': checks,
            'difficulty_status': metadata['difficulty_status'],
            'scope': 'Task and reference identities. Runtime access and participant behavior require separate evidence.'}


def outcome(key, snapshots, truth):
    """Inventory submitted archives for isolated evaluation on the fixed 61-item suite."""
    if key not in KEYS:
        raise ValueError('Unknown formation benchmark task')
    from swarmform.programbench_evaluation import candidate_files
    actors = {}
    for actor, files in snapshots.items():
        versions = []
        for filename, value in sorted(files.items()):
            path = PurePosixPath(filename)
            if PurePosixPath(OUTPUT_ROOT) not in path.parents or path.suffix != '.zip':
                continue
            row = {'path': filename}
            versions.append(row)
            if not isinstance(value, (str, bytes)):
                row['error'] = 'Output must contain actual text or bytes'
                continue
            raw = value.encode() if isinstance(value, str) else value
            row.update(sha256=sha256(raw).hexdigest(), bytes=len(raw))
            try:
                members = candidate_files(raw)
            except ValueError as error:
                row.update(valid_archive=False, error=str(error))
            else:
                row.update(valid_archive=True, files={name: sha256(data).hexdigest()
                           for name, data in sorted(members.items())},
                           quality='isolated_61_item_evaluation_required')
        actors[actor] = {'versions': versions, 'submission_count': len(versions)}
    return {'actors': actors,
            'scope': 'Private terminal outputs. Read/write traces establish authorship, timing and uptake separately.'}
