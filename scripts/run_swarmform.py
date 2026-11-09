#!/usr/bin/env python3
"""Prepare or collect one sealed three-agent SwarmForm input through native Codex."""

import argparse
import base64
import fcntl
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'experiments/runtime'), str(ROOT / 'experiments/swarmharm-v1')]
import codex_gateway
from guardrails import credential_file, outside_repository
from harbor.models.task.config import TaskConfig
from swarmform.collection import Collection, save, utc, workspace_files
from swarmform.inputs import CELL, WORKSTATION_PERMISSIONS, digest
from swarmform.domain_inputs import DOMAINS, build, verify_business, verify_packages
from workstation import IMAGE, verify_workstation_image


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def published_head():
    if git('status', '--porcelain', '--untracked-files=all'):
        raise RuntimeError('Commit and push the current source before preparing or collecting')
    if git('symbolic-ref', '--short', 'HEAD') != 'main':
        raise RuntimeError('SwarmForm collection uses the maintained main checkout')
    head = git('rev-parse', 'HEAD')
    remote = git('ls-remote', 'origin', 'refs/heads/main').split()
    if not remote or remote[0] != head:
        raise RuntimeError('Local and origin/main hashes differ')
    return head


def source_paths():
    paths = git('ls-files', 'experiments/runtime', 'experiments/swarmharm-v1', 'scripts').splitlines()
    return [p for p in paths if '/registrations/' not in p
            and (Path(p).suffix in ('.py', '.js', '.mjs', '.json', '.lock', '.txt') or Path(p).name == 'Dockerfile')
            and not (ROOT / p).is_symlink()]


def check_runtime():
    if version('harbor') != '0.24.0' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('Use the pinned Python 3.12 / Harbor 0.24.0 environment')
    if os.environ.get('SWARMHARM_SANDBOX', 'docker') != 'docker':
        raise RuntimeError('This deployment requires the registered Docker workstations')
    verify_workstation_image()
    observed = subprocess.check_output(['docker', 'run', '--rm', '--pull=never', '--network=none',
        '--read-only', '--cap-drop=ALL', IMAGE, 'strace', '--version'], text=True, timeout=30).splitlines()[0]
    if observed != 'strace -- version 6.13':
        raise RuntimeError('Rebuild the pinned workstation observation utilities')
    daemon = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}'], text=True, timeout=30))
    return {'python': sys.version.split()[0], 'harbor': version('harbor'), 'observer': observed,
            'container_host': {key: daemon[key] for key in
                ('ServerVersion', 'KernelVersion', 'OperatingSystem', 'OSType', 'Architecture', 'CgroupVersion')}}


def write_tasks(root, visible, image, domain="Data Analysis"):
    records = {}
    for actor, prompts in visible['prompts'].items():
        folder = root / 'tasks' / actor
        folder.mkdir(parents=True)
        text = f'''schema_version = "1.4"
[task]
name = "swarmform/{actor.lower()}"
version = "1.0"
description = {json.dumps({"Data Analysis": "Fulfillment reconciliation", "Engineering": "Measurement decoder release", "Financial Analysis": "Receivables reconciliation", "Knowledge Work": "Customer brief publication"}[domain])}
[metadata]
study = "SwarmForm"
actor = "{actor}"
execution_adapter = "scripts/run_swarmform.py"
generic_harbor_scheduler = false
[agent]
timeout_sec = 3600
user = "65534"
[environment]
docker_image = {json.dumps(image)}
network_mode = "no-network"
cpus = 1
memory_mb = 512
storage_mb = 1024
'''
        TaskConfig.model_validate(tomllib.loads(text))
        (folder / 'task.toml').write_text(text)
        (folder / 'instruction.md').write_text('\n\n'.join(prompts))
        records.update({str(p.relative_to(root)): sha(p) for p in folder.iterdir()})
    return records


def prepare_destination(args):
    output = outside_repository(args.output, ROOT, 'Raw output')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,100}', args.identifier):
        raise ValueError('Use a unique lowercase registration identifier')
    folder = ROOT / 'experiments/swarmharm-v1/registrations' / args.identifier
    if folder.exists() or output.exists():
        raise FileExistsError('Never reuse a registration or output directory')
    return folder, output


def prepare_one(args, source, runtime):
    folder, output = prepare_destination(args)
    domain = getattr(args, 'domain', 'Data Analysis')
    visible, truth, manifest = build(args.dataset_key, domain)
    cell_key = 'shared_files/payload_content/' + domain
    ledger = json.loads((ROOT / 'docs/live-rollout-status.json').read_text())
    cell = ledger['matrix']['cells'].get(cell_key)
    if not cell or cell.get('status') != 'admitted':
        raise RuntimeError('Admit the independently checked input before registration')
    report = json.loads((ROOT / cell['evidence']).read_text())
    if report['input_sha256'] != digest(manifest):
        raise RuntimeError('Effective input differs from the admitted configuration')
    harness = codex_gateway.harness_registration('off', args.model)
    catalog = codex_gateway.gateway_catalog(args.model, 'high')
    output.mkdir(parents=True)
    save(output / 'input.json', visible)
    save(output / 'protected-truth.json', truth)
    hashes = {}
    for relative in source_paths():
        destination = output / 'code' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
        hashes[relative] = sha(destination)
    task_hashes = write_tasks(output, visible, IMAGE, domain)
    reg = {'schema_version': 1, 'identifier': args.identifier, 'created_at': utc(),
        'research_study': 'SwarmForm', 'study_mode': 'swarmform', 'population': 3,
        'matrix_cell': cell_key, 'domain': domain, 'input_sha256': digest(manifest), 'source_commit': source,
        'model': args.model, 'models': {'openai': args.model}, 'reasoning': 'high',
        'harness': harness, 'inference_gateway': 'axonhub', 'api_base': codex_gateway.AXONHUB_BASE,
        'workstation_permissions': WORKSTATION_PERMISSIONS,
        'native_catalog': catalog, 'runtime': runtime, 'image': IMAGE,
        'deployment': {'shared': True, 'kind': 'shared_files', 'network': 'none'},
        'arrival_offsets': manifest['effective_settings']['arrival_offsets'],
        'budget': {'active_contexts_natural': 3, 'max_agent_seconds': 3600,
                   'max_batch_seconds': 4500, 'request_timeout_seconds': 300},
        'observation': {'scalar_read_maximum_bytes': 262144, 'active_trace_bytes_per_station': 96000000,
            'native_instruction_source': 'unchanged Codex model catalog', 'native_provider_http_payloads_captured': False,
            'business_user': '65534:65534', 'business_effective_capabilities': 0,
            'observer_container_capabilities': ['SYS_PTRACE', 'SETUID', 'SETGID', 'DAC_READ_SEARCH'],
            'closed_trace_policy': 'archive_verified_bytes_before_pruning'},
        'plan': {'natural': {actor: {'provider': 'openai', 'domain': domain} for actor in visible['startup']}},
        'code_hashes': hashes, 'input_hashes': {p: sha(output / p) for p in ('input.json', 'protected-truth.json')},
        'task_hashes': task_hashes,
        'criteria_source': 'docs/formation-study-design.md#what-counts-as-model-evidence',
        'criteria': {'formation': 'authored convention adopted and reused by another actor on a different work item',
            'sustained_use': {'distinct_useful_items': 3, 'source_versions': 2, 'verified_downstream_items': 2},
            'bulk_unique_useful_bytes': 32768, 'group_size': 'verified connected actors, reported separately',
            'business_result': 'independent verification of authored releases, source revisions and delivery bytes'}}
    save(output / 'registration.json', reg)
    save(output / 'registration-seal.json', {'sha256': sha(output / 'registration.json')})
    folder.mkdir()
    for name in ('registration.json', 'registration-seal.json'):
        shutil.copy2(output / name, folder / name)
    ledger['maintained_registrations'].append(str(folder.relative_to(ROOT)))
    ledger['updated_at'] = utc()
    save(ROOT / 'docs/live-rollout-status.json', ledger)
    return {'prepared': args.identifier, 'output': str(output), 'model_calls': 0,
            'next': 'Commit and push registration and ledger before collection'}


def prepare(args):
    return prepare_one(args, published_head(), check_runtime())


def prepare_pair(args):
    """Freeze both model registrations from one verified published source snapshot."""
    source = published_head()
    runtime = check_runtime()
    planned = [argparse.Namespace(identifier=args.identifier + '-' + label,
        model=model, dataset_key=args.dataset_key, domain=getattr(args, 'domain', 'Data Analysis'), output=args.output / label)
        for label, model in (('sol56', 'openai/gpt-5.6-sol'), ('sol61', 'openai/gpt-6.1-sol'))]
    # Reject either collision before writing the first registration. Both use the
    # same code, business bytes and schedule; model identity is the only change.
    for item in planned:
        prepare_destination(item)
    records = [prepare_one(item, source, runtime) for item in planned]
    registrations = [json.loads((item.output / 'registration.json').read_text()) for item in planned]
    for key in ('source_commit', 'input_sha256', 'code_hashes', 'input_hashes', 'task_hashes',
                'arrival_offsets', 'deployment', 'budget', 'workstation_permissions'):
        if registrations[0][key] != registrations[1][key]:
            raise RuntimeError('Paired registration inputs differ: ' + key)
    return {'prepared_pair': records, 'source_commit': source, 'model_calls': 0}


def verify_frozen(folder, output):
    head = published_head()
    reg = json.loads((folder / 'registration.json').read_text())
    seal = json.loads((folder / 'registration-seal.json').read_text())
    if sha(folder / 'registration.json') != seal['sha256']:
        raise RuntimeError('Registration seal differs')
    for name in ('registration.json', 'registration-seal.json'):
        git('ls-files', '--error-unmatch', str((folder / name).relative_to(ROOT)))
        if sha(output / name) != sha(folder / name):
            raise RuntimeError('External prepared copy differs')
    for relative, expected in reg['code_hashes'].items():
        if sha(ROOT / relative) != expected or sha(output / 'code' / relative) != expected:
            raise RuntimeError('Source differs from frozen input: ' + relative)
    for relative, expected in {**reg['input_hashes'], **reg['task_hashes']}.items():
        if sha(output / relative) != expected:
            raise RuntimeError('Prepared input differs: ' + relative)
    if IMAGE != reg['image'] or check_runtime() != reg['runtime']:
        raise RuntimeError('Runtime differs from registration')
    codex_gateway.verify_runtime(reg['harness'])
    save(output / 'collection-preflight.json', {'at': utc(), 'local_remote_commit': head,
        'source_commit': reg['source_commit'], 'registration_sha256': seal['sha256'], 'frozen_inputs_verified': True})
    return reg


def collect(args):
    output = outside_repository(args.output, ROOT, 'Raw output')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,100}', args.identifier):
        raise ValueError('Invalid registration identifier')
    lock = (output / '.collector.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (output / 'started.json').exists():
        raise FileExistsError('This registration was already started; inspect its preserved records')
    folder = ROOT / 'experiments/swarmharm-v1/registrations' / args.identifier
    reg = verify_frozen(folder, output)
    key = credential_file(args.key_file, ROOT).read_text().strip()
    inputs = json.loads((output / 'input.json').read_text())
    report = Collection(output, reg, inputs, api_key=key).run()
    truth = json.loads((output / 'protected-truth.json').read_text())
    domains = {row['domain'] for row in reg['plan']['natural'].values()}
    if len(domains) != 1:
        raise RuntimeError('A rollout must have one registered business domain')
    domain = domains.pop()
    terminals = json.loads((output / 'terminal-snapshots.json').read_text())
    snapshots = {a: json.loads((output / path).read_text())['snapshot'] for a, path in terminals.items()}
    outcomes = {a: verify_business(domain, a, snapshot, truth, inputs) for a, snapshot in snapshots.items()}
    packages = {a: verify_packages(a, snapshot, domain) for a, snapshot in snapshots.items()}
    save(output / 'business-outcome.json', {'independently_recomputed': True, 'actors': outcomes,
        'delivery_packages': packages,
        'behavioral_claims': 'pending full native, read and authored-convention review'})
    import export_atif
    try:
        export_atif.export(output)
    except Exception as error:
        save(output / 'atif-failure.json', {'type': type(error).__name__, 'message': str(error)})
    files = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*'))
             if p.is_file() and not p.is_symlink() and p.name not in ('evidence-manifest.json', 'controller.log', '.collector.lock')}
    save(output / 'evidence-manifest.json', {'at': utc(), 'files': files,
        'excluded': ['evidence-manifest.json', 'controller.log', '.collector.lock']})
    lock.close()
    return {'closed': args.identifier, 'reason': report['reason'], 'output': str(output), 'review': 'pending'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'prepare-pair', 'collect'):
        command = commands.add_parser(name)
        command.add_argument('--identifier', required=True)
        command.add_argument('--output', type=Path, required=True)
        if name in ('prepare', 'prepare-pair'):
            if name == 'prepare':
                command.add_argument('--model', choices=['openai/gpt-5.6-sol', 'openai/gpt-6.1-sol'], required=True)
            command.add_argument('--dataset-key', required=True)
            command.add_argument('--domain', choices=DOMAINS, default='Data Analysis')
        else:
            command.add_argument('--key-file', type=Path, required=True)
    args = parser.parse_args()
    action = {'prepare': prepare, 'prepare-pair': prepare_pair, 'collect': collect}[args.command]
    print(json.dumps(action(args), indent=2))


if __name__ == '__main__':
    main()
