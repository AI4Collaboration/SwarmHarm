"""Verify saved model-free controls, frozen inputs, source identity and cleanup."""
import argparse
import base64
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=HERE/'evidence/2026-10-21/verification-final.json')
    args = parser.parse_args()
    assert not args.output.exists(), 'Evidence is write-once; use a fresh destination.'
    evidence = args.output.parent
    evidence.mkdir(parents=True, exist_ok=True)
    suites = [
        ('infra-reader-checks-final-2026-10-21.log', 12),
        ('business-v3-checks-final-2026-10-21.log', 13),
        ('business-v3-flow-final-2026-10-21.log', 7),
        ('business-v3-multicall-final-2026-10-21.log', 1),
        ('business-v3-launch-final-2026-10-21.log', 1),
        ('infra-prompt-contract-2026-10-21.log', 19),
    ]
    verified_suites = []
    all_methods = []
    for name, count in suites:
        source = REPO.parent/'eval-readiness'/name
        body = source.read_text()
        matches = re.findall(r'^test_\S+.* \.\.\. ok$', body, re.M)
        assert len(matches) == count, (name, len(matches))
        assert re.search(r'^Ran '+str(count)+r' tests? in ', body, re.M), name
        assert body.rstrip().endswith('OK') and 'ResourceWarning' not in body, name
        target = evidence/'logs'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert target.read_bytes() == source.read_bytes()
        else:
            target.write_bytes(source.read_bytes())
        all_methods.extend(matches)
        verified_suites.append({'log': str(target.relative_to(REPO)), 'tests': count, 'sha256': digest(target)})
    assert len(set(all_methods)) == len(all_methods) == 53

    spec = importlib.util.spec_from_file_location('verified_business_v3', REPO/'experiments/business-cache-v3/lab.py')
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    registration = REPO/'experiments/business-cache-v2/registrations/2026-10-21-sol56-r2'
    reg = load(registration/'registration.json')
    fixtures = load(REPO/'experiments/business-cache-v3/fixtures.json')
    assert (REPO/'experiments/business-cache-v3/fixtures.json').read_bytes() == (REPO/'experiments/business-cache-v2/fixtures.json').read_bytes()
    inputs, files = load(registration/'initial-input-audit.json'), load(registration/'initial-file-audit.json')
    contract = []
    for phase, plan in reg['plan'].items():
        for actor, item in plan.items():
            assert lab.initial(fixtures, plan, actor) == inputs[phase][actor], actor
            assert lab.files(fixtures, item) == files[phase][actor], actor
            contract.append({'phase': phase, 'actor': actor, 'native_input_equal': True, 'initial_files_equal': True})
    packet = REPO/'experiments/business-cache-v2/results/2026-10-21-sol56-partial'
    frozen = []
    for name, expected in reg['code_hashes'].items():
        assert digest(REPO/name) == digest(packet/'code'/name) == expected, name
        frozen.append(name)
    assert len(frozen) == 13
    stress = load(HERE/'evidence/2026-10-21/stress-final.json')
    baseline = load(HERE/'evidence/2026-10-21/baseline.json')
    assert stress['passed'] and stress['model_calls'] == baseline['model_calls'] == 0
    assert stress['infra_source_sha256'] == digest(HERE/'reader.py')
    assert stress['program_sha256'] == baseline['program_sha256'] == sha256(lab.PUBLIC_READER.encode()).hexdigest()
    assert stress['summary']['observations'] == 1320
    assert stress['reader_only_retries'] == 0 and stress['real_stage_timeouts'] == []
    assert all(x['closed'] for x in stress['workstations'])
    world = load(packet/'natural/world.json')
    shared = world['shared_files']
    decoded_bytes = sum(len(base64.b64decode(v['data'])) for v in shared.values())
    assert decoded_bytes == 2528
    # This is the actual global inference lock used by collect(), not an export-local file.
    lock_path = REPO.parent/'eval-readiness/release-campaign-inference.lock'
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_UN)
    names = stress['verified_cleaned_reader_containers'] + [x['name'] for x in stress['workstations']]
    inspected = subprocess.run(['docker', 'inspect', *names], capture_output=True, text=True, timeout=30)
    assert inspected.returncode != 0 and json.loads(inspected.stdout) == []
    assert len(inspected.stderr.splitlines()) == len(names)
    assert all('no such' in line.lower() for line in inspected.stderr.splitlines())
    listed = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}'], capture_output=True, text=True, timeout=15, check=True)
    containers = listed.stdout.splitlines()
    assert not any(n.startswith(('sh-public-reader-', 'sh-business-reader-', 'sh-workbench-')) for n in containers)
    result = {
        'verified_at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'model_calls': 0,
        'scope': 'Local infrastructure repair; no resumed/replaced trajectory or new behavioral result.',
        'test_count': len(all_methods), 'suites': verified_suites,
        'frozen_native_inputs_and_initial_files': contract,
        'unchanged_historical_source_files': frozen,
        'source_hashes': {str(p.relative_to(REPO)): digest(p) for folder in (HERE, REPO/'experiments/business-cache-v3') for p in sorted(folder.glob('*.py'))},
        'decoder_sha256': stress['program_sha256'], 'historical_public_files': len(shared),
        'historical_decoded_public_bytes': decoded_bytes, 'baseline': baseline['summary'],
        'stress': {**stress['summary'], 'elapsed_seconds': stress['elapsed_seconds'],
                   'paused_workstations': 6, 'workstation_commands': 60,
                   'stage_timeouts': 0, 'reader_only_retries': 0},
        'cleanup': {'reader_containers_verified_absent': len(stress['verified_cleaned_reader_containers']),
                    'workstations_verified_absent': len(stress['workstations']),
                    'owned_prefixes_absent': True, 'remaining_containers': containers,
                    'actual_inference_lock_available': True},
        'hosted_runtime_upgraded_or_restarted': False, 'new_credentials': False,
        'limits': ['The original Docker substage was not recorded and its isolated stall did not recur in baseline probes.',
                   'Business v3 is verified offline; a fresh registration, native preflight and capabilities are required before real-model collection.',
                   'Historical business v2 collection remains partial.'],
    }
    lab.infra.atomic_json(args.output, result)
    print(json.dumps({'passed': True, 'tests': len(all_methods), 'input_contexts': len(contract), 'stress': stress['summary'], 'owned_containers_absent': len(names), 'model_calls': 0}))


if __name__ == '__main__':
    main()
