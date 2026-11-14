"""Plan or collect the maintained SwarmHarm inputs at N=4, 8 and 16."""
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
                               harness='codex', reasoning_effort='high', goal_mode='off',
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
        'codex', row['mechanism'], row['scenario'])}
    for record in records:
        output = Path(record['output'])
        if not (output/'controls.json').is_file() or not (output/'registration-seal.json').is_file():
            continue
        checks = run.load(output/'controls.json')
        if checks.get('passed') and required <= set(checks.get('check_modules', [])):
            # Preparation also verifies source, image, runtime and every sealed hash.
            return ['--controls-from', str(output)]
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, help='Exact model ID in the native Codex catalog')
    parser.add_argument('--base-url', default=os.environ.get('OPENAI_BASE_URL', run.AXONHUB_API_BASE))
    parser.add_argument('--key-file', type=Path, default=os.environ.get('OPENAI_API_KEY_FILE'))
    parser.add_argument('--populations', nargs='+', type=int, default=[4, 8, 16])
    parser.add_argument('--scenarios', nargs='+', choices=['engineering-capacity', 'knowledge-work'],
                        default=['engineering-capacity', 'knowledge-work'])
    parser.add_argument('--mechanisms', nargs='+', type=mechanism_inputs.configuration_id,
                        choices=mechanism_inputs.CURRENT_CONFIGURATIONS,
                        default=list(mechanism_inputs.CURRENT_CONFIGURATIONS))
    parser.add_argument('--startup-concurrency', type=int, default=8)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--out', type=Path, help='Batch directory outside Git')
    parser.add_argument('--execute', action='store_true', help='Register, commit each registration and collect sequentially')
    args = parser.parse_args()
    if min(args.populations) < 2 or args.repeats < 1 or args.startup_concurrency < 1:
        parser.error('Use N >= 2, positive repeats and positive startup concurrency')
    for values in (args.populations, args.scenarios, args.mechanisms):
        if len(values) != len(set(values)):
            parser.error('Selections must not contain duplicates')
    args.base_url = run.guardrails.api_base_url(args.base_url)
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
    if (root/'plan.json').exists() and run.load(root/'plan.json') != rows:
        parser.error('This output root contains a different plan; choose a fresh --out')
    for identity in ('GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT'):
        subprocess.run(['git', 'var', identity], cwd=run.REPO, check=True, stdout=subprocess.DEVNULL)
    run.save(root/'plan.json', rows)
    model_slug = re.sub(r'[^\w.-]+', '-', args.model).strip('.-') or 'model'
    group = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    records = []
    key = args.key_file
    temporary_key = None
    if key is None:
        credential = os.environ.get('OPENAI_API_KEY')
        if not credential:
            parser.error('Set OPENAI_API_KEY, OPENAI_API_KEY_FILE or --key-file')
        with tempfile.NamedTemporaryFile(mode='w', prefix='swarmharm-key-', delete=False) as stream:
            stream.write(credential+'\n')
            temporary_key = key = Path(stream.name)
    key = key.expanduser().resolve()
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
                common = ['--output', str(output), '--registration-dir', str(registration), '--key-file', str(key)]
                run.save(root/'index.json', {'study': 'swarmharm', 'runs': [*records, {**record, 'status': 'running'}]})
                print('Starting:', output, flush=True)
                try:
                    command([sys.executable, str(run.HERE/'run.py'), '--phase', 'prepare',
                             '--source-retention', 'local', '--scenario', row['scenario'],
                             '--mechanism', row['mechanism'], '--model-id', args.model,
                             '--api-base', args.base_url, '--harness', 'codex', '--goal-mode', 'off',
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
            run.save(root/'index.json', {'study': 'swarmharm', 'runs': records})
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
