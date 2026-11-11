"""Fresh registrations and isolated execution of an exact accepted input package."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

CONTROLLER_FILES = ('swarmform/scripts/run_swarmform.py', 'swarmform/scripts/swarmform_accepted_run.py',
                    'swarmform/scripts/swarmform_delivery_export.py', 'swarmform/scripts/swarmform_scope.py')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def member(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected a relative sealed package path')
    result = Path(root) / path
    if result.is_symlink() or not result.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Package member escapes its root')
    return result


def verify_files(root, hashes):
    for name, expected in hashes.items():
        if sha(member(root, name)) != expected:
            raise ValueError('Sealed bytes differ: ' + name)


def verify_code(root, hashes):
    actual = {p.relative_to(root).as_posix() for p in Path(root).rglob('*') if p.is_file()}
    if actual != set(hashes):
        raise ValueError('Frozen code contains missing or unsealed files')
    verify_files(root, hashes)


def admitted(entry, reg):
    ledger = read(entry.ROOT / 'swarmform/docs/live-rollout-status.json')
    cell = ledger['matrix']['cells'].get(reg['matrix_cell'], {})
    report = read(member(entry.ROOT, cell['evidence']))
    if (cell.get('status') != 'admitted' or report.get('status') != 'admitted'
            or report.get('matrix_cell') != reg['matrix_cell']
            or report.get('input_sha256') != reg['input_sha256']):
        raise ValueError('Accepted package no longer matches the current admission')
    return ledger


def accepted_result(entry, original):
    from swarmform_delivery_export import is_final, communication_result
    ledger = admitted(entry, original)
    cell = ledger['matrix']['cells'][original['matrix_cell']]
    result = cell.get('current_model_result', {})
    if (not is_final(cell) or result.get('identifier') != original['identifier']
            or result.get('input_sha256') != original['input_sha256']
            or not result.get('trajectory_url') or not result.get('archive_sha256')):
        raise ValueError('Package is not the current qualifying accepted result')
    communication = communication_result(result)
    positive = communication.get('three_agent_swarm') and communication.get('sustained_substantive_exchange')
    retained = entry.ROOT / 'swarmform/registrations' / original['identifier']
    return {'rollout': original['identifier'], 'input_sha256': original['input_sha256'],
            'registration_sha256': sha(retained / 'registration.json'),
            'trajectory_url': result['trajectory_url'], 'trajectory_sha256': result['archive_sha256'],
            'acceptance': 'sustained_communication' if positive else 'reviewed_negative'}


def package_input(entry, package):
    package = Path(package).expanduser().resolve()
    bundle = package.parents[2]
    reg = read(package / 'registration.json')
    seal = read(package / 'registration-seal.json')['sha256']
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,100}', reg['identifier']):
        raise ValueError('Invalid accepted registration identifier')
    original = entry.ROOT / 'swarmform/registrations' / reg['identifier']
    if (sha(package / 'registration.json') != seal
            or sha(original / 'registration.json') != seal
            or read(original / 'registration-seal.json')['sha256'] != seal):
        raise ValueError('Accepted registration differs from published provenance')
    rows = [row for row in read(bundle / 'index.json')['cells']
            if row['cell'] == reg['matrix_cell']]
    if len(rows) != 1:
        raise ValueError('Expected one accepted index row')
    row = rows[0]
    if (row.get('acceptance') not in ('sustained_communication', 'reviewed_negative')
            or row['directory'] != package.relative_to(bundle).as_posix()
            or row['source'] != 'sources/' + reg['source_commit']
            or row['registration_sha256'] != seal or row['input_sha256'] != reg['input_sha256']):
        raise ValueError('Accepted index binding differs')
    manifest = read(package / 'input-manifest.json')
    if entry.digest(manifest) != reg['input_sha256']:
        raise ValueError('Accepted input manifest differs')
    verify_files(package, reg['input_hashes'] | reg['task_hashes'])
    source = member(bundle, row['source'])
    verify_files(source, reg['code_hashes'])
    selection = accepted_result(entry, reg)
    if any(row.get(key) != value for key, value in selection.items()):
        raise ValueError('Index differs from the current accepted trajectory')
    return reg, source, selection


def dispatch(action, code, registration, *, output=None, key_file=None):
    argv = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), action,
            str(Path(code).resolve()), str(Path(registration).resolve())]
    if output is not None:
        argv.append(str(Path(output).resolve()))
    if key_file is not None:
        argv.append(str(Path(key_file).resolve()))
    return json.loads(subprocess.check_output(argv, text=True))


def prepare(entry, args, controller_commit):
    folder, output = entry.prepare_destination(args)
    package = Path(args.accepted_package).expanduser().resolve()
    original, source, selection = package_input(entry, package)
    requested_cell = '/'.join((args.deployment, args.encoding, args.domain))
    if (requested_cell != original['matrix_cell'] or args.model != original['model']
            or args.dataset_key != 'november' or args.identifier == original['identifier']):
        raise ValueError('Use a fresh identifier and the accepted cell, model and November dataset')
    output.mkdir(parents=True)
    for name in original['input_hashes'] | original['task_hashes']:
        destination = member(output, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(member(package, name), destination)
    shutil.copyfile(package / 'input-manifest.json', output / 'input-manifest.json')
    for name in original['code_hashes']:
        destination = member(output / 'code', name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(member(source, name), destination)
    for name in ('registration.json', 'registration-seal.json'):
        shutil.copyfile(package / name, output / ('accepted-original-' + name))
    verify_files(output, original['input_hashes'] | original['task_hashes'])
    verify_code(output / 'code', original['code_hashes'])
    runtime = dispatch('inspect', output / 'code', output / 'accepted-original-registration.json')
    reg = deepcopy(original)
    reg.update(identifier=args.identifier, created_at=entry.utc(), runtime=runtime)
    reg['accepted_package'] = {
        'original_identifier': original['identifier'],
        'original_registration_sha256': sha(package / 'registration.json'),
        'input_manifest_sha256': sha(output / 'input-manifest.json'),
        'controller_commit': controller_commit,
        'controller_code_hashes': {name: sha(entry.ROOT / name) for name in CONTROLLER_FILES},
        'execution': 'isolated_process_from_exact_frozen_code',
        'accepted_result': selection,
    }
    entry.save(output / 'registration.json', reg)
    entry.save(output / 'registration-seal.json', {'sha256': sha(output / 'registration.json')})
    folder.mkdir()
    for name in ('registration.json', 'registration-seal.json'):
        shutil.copyfile(output / name, folder / name)
    ledger = admitted(entry, reg)
    ledger['maintained_registrations'].append(str(folder.relative_to(entry.ROOT)))
    ledger['updated_at'] = entry.utc()
    entry.save(entry.ROOT / 'swarmform/docs/live-rollout-status.json', ledger)
    return {'prepared': args.identifier, 'output': str(output), 'model_calls': 0,
            'accepted_source_commit': reg['source_commit'],
            'next': 'Commit and push the fresh registration and ledger before collection'}


def verify_prepared(entry, reg, output, published_head, registration_sha):
    provenance = reg['accepted_package']
    original_path = output / 'accepted-original-registration.json'
    original = read(original_path)
    if (sha(original_path) != provenance['original_registration_sha256']
            or read(output / 'accepted-original-registration-seal.json')['sha256'] != sha(original_path)
            or original['identifier'] != provenance['original_identifier']
            or reg['identifier'] == original['identifier']):
        raise ValueError('Accepted source registration differs')
    retained = entry.ROOT / 'swarmform/registrations' / original['identifier']
    if sha(retained / 'registration.json') != sha(original_path):
        raise ValueError('Accepted source differs from published registration')
    if {k: v for k, v in reg.items() if k not in ('identifier', 'created_at', 'runtime', 'accepted_package')} != {
            k: v for k, v in original.items() if k not in ('identifier', 'created_at', 'runtime', 'accepted_package')}:
        raise ValueError('Fresh registration changes accepted input or runtime pins')
    admitted(entry, reg)
    if accepted_result(entry, original) != provenance['accepted_result']:
        raise ValueError('Current accepted result changed after preparation')
    if set(provenance['controller_code_hashes']) != set(CONTROLLER_FILES):
        raise ValueError('Accepted launcher seal is incomplete')
    verify_files(entry.ROOT, provenance['controller_code_hashes'])
    verify_code(output / 'code', reg['code_hashes'])
    verify_files(output, reg['input_hashes'] | reg['task_hashes'])
    if (sha(output / 'input-manifest.json') != provenance['input_manifest_sha256']
            or entry.digest(read(output / 'input-manifest.json')) != reg['input_sha256']):
        raise ValueError('Prepared accepted manifest differs')
    if dispatch('inspect', output / 'code', output / 'registration.json') != reg['runtime']:
        raise RuntimeError('Frozen runtime differs from the fresh registration')
    entry.save(output / 'collection-preflight.json', {
        'at': entry.utc(), 'local_remote_commit': published_head,
        'source_commit': reg['source_commit'], 'registration_sha256': registration_sha,
        'frozen_inputs_verified': True, 'accepted_package': provenance})
    return reg


def frozen_entry(code, reg):
    # -I excludes caller PYTHONPATH/cwd; only sealed code enters these namespaces.
    verify_code(code, reg['code_hashes'])
    # The registered image may have overridden the historical source default.
    os.environ['SWARMHARM_DOCKER_IMAGE'] = reg['image']
    sys.path.insert(0, str(code / 'scripts'))
    spec = importlib.util.spec_from_file_location('accepted_frozen_runner', code / 'swarmform/scripts/run_swarmform.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != (code / 'swarmform/scripts/run_swarmform.py').resolve():
        raise RuntimeError('Frozen runner import escaped its sealed source')
    return module


def worker(argv):
    action, code, registration, *rest = argv
    code = Path(code).resolve()
    reg = read(registration)
    entry = frozen_entry(code, reg)
    if action == 'inspect':
        if entry.IMAGE != reg['image']:
            raise RuntimeError('Frozen image differs from accepted registration')
        runtime = entry.check_runtime()
        entry.codex_gateway.verify_runtime(reg['harness'])
        if entry.codex_gateway.gateway_catalog(reg['model'], reg['reasoning']) != reg['native_catalog']:
            raise RuntimeError('Native model catalog differs from accepted registration')
        return runtime
    if action != 'collect' or len(rest) != 2:
        raise ValueError('Expected inspect or collect')
    output, key_file = map(Path, rest)
    if (output / 'started.json').exists():
        raise FileExistsError('This fresh registration was already started')
    preflight = read(output / 'collection-preflight.json')
    if (preflight.get('registration_sha256') != sha(registration)
            or preflight.get('source_commit') != reg['source_commit']
            or preflight.get('frozen_inputs_verified') is not True):
        raise ValueError('Accepted collection requires the outer published preflight')
    verify_files(output, reg['input_hashes'] | reg['task_hashes'])
    inputs = read(output / 'input.json')
    key = entry.credential_file(key_file, entry.ROOT).read_text().strip()
    report = entry.Collection(output, reg, inputs, api_key=key).run()
    return entry.finalize_collection(output, reg, inputs, report)


if __name__ == '__main__':
    print(json.dumps(worker(sys.argv[1:])))
