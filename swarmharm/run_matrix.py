"""Single-model SwarmHarm component. Use scripts/run-evals for the full default lineup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import run
import model_lineup as defaults
import batch_resume
from phase2 import mechanism_inputs


def source_digest():
    digest = hashlib.sha256()
    for path in sorted(set(run.code_paths())):
        digest.update(path.relative_to(run.REPO).as_posix().encode()+b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def cases(args, source):
    for population in args.populations:
        for replicate in range(1, args.repeats+1):
            for scenario in args.scenarios:
                for mechanism in args.mechanisms:
                    yield dict(population=population, replicate=replicate,
                               scenario=scenario, mechanism=mechanism, model=args.model,
                               api_base=args.base_url, source_sha256=source,
                               harness=run.guardrails.native_harness({'model':args.model}),
                               api_protocol=getattr(args, 'api_protocol', 'chat-completions'),
                               served_model=getattr(args, 'served_model', None) or args.model, reasoning_effort='high', goal_mode='off',
                               codex_auth=getattr(args,'codex_auth','api'),
                               startup_concurrency=min(population, args.startup_concurrency))


def run_id(row):
    suffix = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
    return f"{row['scenario']}-{row['mechanism']}-r{row['replicate']}-{suffix}"


def existing_status(output):
    """Never restart an existing directory, including an incomplete attempt."""
    archived = output.with_name(output.name+'.archive.json')
    if not output.exists() and archived.is_file():
        metadata = run.load(archived)
        present = Path(metadata['archive']).is_file()
        return dict(status='archived' if present else 'archive_missing',
                    archive=metadata['archive'], sha256=metadata['sha256'])
    if output.exists():
        completion = output/'completion.json'
        status = run.load(completion).get('status') if completion.is_file() else 'incomplete'
        reviewed = all((output/name).is_file() for name in
                       ('evidence-manifest.json', 'independent-review.json'))
        return dict(status=status if reviewed else 'review_incomplete',
                    collection_status=status, review='complete' if reviewed else 'pending')
    return None


def reusable_controls(records, row):
    required = {str(path.relative_to(run.HERE)) for path in run.preparation_check_paths(
        row['harness'], row['mechanism'], row['scenario'])}
    expected_source = {str(path.relative_to(run.REPO)): run.sha(path) for path in run.code_paths()}
    for record in records:
        output = Path(record['output'])
        if not all((output/name).is_file() for name in
                   ('controls.json', 'registration.json', 'registration-seal.json')):
            continue
        if run.load(output/'registration.json').get('code_hashes') != expected_source:
            continue
        checks = run.load(output/'controls.json')
        if checks.get('passed') and required <= set(checks.get('check_modules', [])):
            # Preparation also verifies source, image, runtime and every sealed hash.
            return ['--controls-from', str(output)]
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-protocol', choices=('chat-completions','native'), default='chat-completions')
    parser.add_argument('--served-model', help='Exact provider ID, if different from native identity')
    parser.add_argument('--codex-auth',choices=('chatgpt','api'),default='chatgpt')
    parser.add_argument('--resume', action='store_true', help='Retain existing attempts while selecting populations')
    parser.add_argument('--model', required=True, help='Selected model identity; see docs/model-lineup.md')
    parser.add_argument('--base-url', default=os.environ.get('OPENAI_BASE_URL', run.AXONHUB_API_BASE))
    parser.add_argument('--key-file', type=Path, default=os.environ.get('OPENAI_API_KEY_FILE'))
    parser.add_argument('--populations', nargs='+', type=int, default=list(defaults.POPULATIONS))
    parser.add_argument('--scenarios', nargs='+', choices=['engineering-capacity', 'knowledge-work'],
                        default=list(defaults.SCENARIOS))
    parser.add_argument('--mechanisms', nargs='+', type=mechanism_inputs.configuration_id,
                        choices=mechanism_inputs.CURRENT_CONFIGURATIONS,
                        default=list(map(mechanism_inputs.configuration_id, defaults.MECHANISMS)))
    parser.add_argument('--startup-concurrency', type=int, default=8)
    parser.add_argument('--repeats', type=int, default=defaults.REPEATS)
    parser.add_argument('--out', type=Path, help='Batch directory outside Git')
    parser.add_argument('--execute', action='store_true', help='Register, commit each registration and collect sequentially')
    args = parser.parse_args()
    subscription=run.guardrails.native_harness({'model':args.model})=='codex' and args.codex_auth=='chatgpt'
    if subscription:
        args.api_protocol='native';args.served_model=args.model.removeprefix('openai/');args.key_file=None;args.base_url=None
    if min(args.populations) < 2 or args.repeats < 1 or args.startup_concurrency < 1:
        parser.error('Use N >= 2, positive repeats and positive startup concurrency')
    for values in (args.populations, args.scenarios, args.mechanisms):
        if len(values) != len(set(values)):
            parser.error('Selections must not contain duplicates')
    if not subscription:args.base_url = run.guardrails.api_base_url(args.base_url)
    if args.execute and (args.out is None or args.out.resolve().is_relative_to(run.REPO)):
        parser.error('--execute requires --out outside the repository')
    rows = list(cases(args, source_digest()))
    if not args.execute:
        for row in rows:
            print(json.dumps(row, sort_keys=True))
        return 0
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=run.REPO, text=True).strip():
        parser.error('Commit source changes before collecting')
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=True)
    try: rows = batch_resume.prepare(root, rows, args.resume)
    except ValueError as error: parser.error(str(error))
    for identity in ('GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT'):
        subprocess.run(['git', 'var', identity], cwd=run.REPO, check=True, stdout=subprocess.DEVNULL)
    model_slug = re.sub(r'[^\w.-]+', '-', args.model).strip('.-') or 'model'
    group = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    records = []
    key = args.key_file
    temporary_key = None
    if key is None and not subscription:
        credential = os.environ.get('OPENAI_API_KEY')
        if not credential:
            parser.error('Set OPENAI_API_KEY, OPENAI_API_KEY_FILE or --key-file')
        with tempfile.NamedTemporaryFile(mode='w', prefix='swarmharm-key-', delete=False) as stream:
            stream.write(credential+'\n')
            temporary_key = key = Path(stream.name)
    key = key.expanduser().resolve() if key else None
    failures = 0
    try:
        for row in rows:
            name = run_id(row)
            output = root/model_slug/f"n{row['population']}"/name
            registration = run.REGISTRATIONS/f"batch-{group}-{name}"
            record = {**row, 'output': str(output), 'registration': str(registration)}
            completion = output/'completion.json'
            existing = existing_status(output)
            if existing is not None:
                record.update(existing)
                failures += int(existing['status'] not in ('collected', 'collected_with_limits', 'archived'))
                print('Preserved existing attempt:', output, flush=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                log = output.with_name(name+'.log')
                def command(argv):
                    with log.open('a') as stream:
                        subprocess.run(argv, cwd=run.REPO, stdout=stream,
                                       stderr=subprocess.STDOUT, check=True)
                common = ['--output', str(output), '--registration-dir', str(registration)]
                if key:common += ['--key-file',str(key)]
                batch_resume.save_index(root, 'swarmharm', [*records, {**record, 'status': 'running'}])
                print('Starting:', output, flush=True)
                try:
                    command([sys.executable, str(run.HERE/'run.py'), '--phase', 'prepare',
                             '--source-retention', 'local', '--scenario', row['scenario'],
                             '--mechanism', row['mechanism'], '--model-id', args.model,
                             *(['--api-base',args.base_url] if args.base_url else []), '--harness', row['harness'],
                             '--api-protocol', row['api_protocol'], '--served-model', row['served_model'], '--goal-mode', 'off',
                             '--codex-auth',args.codex_auth,
                             '--reasoning-effort', 'high', '-N', str(row['population']),
                             '--startup-concurrency', str(row['startup_concurrency']),
                             *reusable_controls(records, row), *common])
                    command(['git', 'add', '--', str(registration)])
                    command(['git', 'commit', '-m', f'Register {registration.name}'])
                    command([sys.executable, str(run.HERE/'run.py'), '--phase', 'collect', *common])
                    record['status'] = run.load(completion)['status']
                    if record['status'] in ('collected', 'collected_with_limits'):
                        command([sys.executable, str(output/'code/shared/export_atif.py'), str(output)])
                        command([sys.executable, str(output/'code/swarmharm/review.py'), '--output', str(output)])
                        record['review'] = 'complete'
                    else:
                        failures += 1
                except subprocess.CalledProcessError as error:
                    record.update(status='command_failed', returncode=error.returncode, log=str(log))
                    failures += 1
                if output.exists():
                    record['raw_bytes'] = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
            records.append(record)
            batch_resume.save_index(root, 'swarmharm', records)
            # A partial registration must be inspected before another preparation.
            if subprocess.check_output(['git', 'status', '--porcelain'], cwd=run.REPO, text=True).strip():
                print('Stopped after an incomplete registration; see the batch index.', file=sys.stderr)
                return 1
    finally:
        if temporary_key:
            temporary_key.unlink(missing_ok=True)
    return int(failures != 0)


if __name__ == '__main__':
    raise SystemExit(main())
