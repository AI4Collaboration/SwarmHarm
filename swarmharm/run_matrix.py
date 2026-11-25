"""Single-model SwarmHarm component. Use scripts/run-evals for the full default lineup."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

import run
import model_lineup as defaults
import launch_capacity
from process_control import run_process
from phase2 import mechanism_inputs

REVIEWABLE_COLLECTION_STATUSES = frozenset({'collected', 'collected_with_limits', 'rollout_limit'})
RETRYABLE_COLLECTION_STATUSES = frozenset({'collector_error', 'provider_hold', 'observer_hold', 'incomplete'})
PERMANENT_LOG_MARKERS = ('HTTP Error 401', 'HTTP Error 403', 'Model blocked by guardrail',
                         'Provider not allowed by guardrail', 'Unknown model family',
                         'Invalid served model ID', 'Invalid local transport credential')


def source_digest():
    digest = hashlib.sha256()
    for path in sorted(set(run.code_paths())):
        digest.update(path.relative_to(run.REPO).as_posix().encode()+b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def cases(args, source):
    ledger = run.load(run.HERE/'docs/research/mechanism-input-status.json')
    workloads = {(row['domain'], row['mechanism']): row.get('selected_workload') or row['domain']
                 for row in ledger['inputs'] if row['current_input_validation'] in ('reviewed_positive', 'path_validated')}
    coupling = getattr(args, 'coupling', 'coupled')
    explicit_variant = getattr(args, 'input_variant', None)
    variant_suite = getattr(args, 'variant_suite', 'main')
    if coupling == 'uncoupled' and (explicit_variant is not None or variant_suite != 'main'):
        raise ValueError('Choose --coupling uncoupled, --input-variant, or --variant-suite extended/all, not combinations')
    if explicit_variant is not None and variant_suite != 'main':
        raise ValueError('Choose --input-variant or --variant-suite extended/all, not both')
    def make_row(population, replicate, scenario, workload, mechanism, variant=None):
        row = dict(population=population, replicate=replicate,
                   scenario=scenario, workload=workload,
                   mechanism=mechanism, model=args.model,
                   api_base=args.base_url, source_sha256=source,
                   harness=run.guardrails.native_harness({'model':args.model}),
                   api_protocol=getattr(args, 'api_protocol', 'chat-completions'),
                   served_model=getattr(args, 'served_model', None) or args.model, reasoning_effort='high', goal_mode='off',
                   startup_concurrency=min(population, args.startup_concurrency))
        if variant is not None:
            row['input_variant'] = variant
        return row
    for population in args.populations:
        for replicate in range(1, args.repeats+1):
            if variant_suite in ('main', 'all'):
                for scenario in args.scenarios:
                    for mechanism in args.mechanisms:
                        workload = workloads[scenario, mechanism]
                        variant = (mechanism_inputs.uncoupled_variant(mechanism, workload)
                                   if coupling == 'uncoupled' else explicit_variant)
                        if variant is not None and (mechanism, workload, variant) not in mechanism_inputs.INPUT_VARIANTS:
                            raise ValueError(f'--input-variant {variant} does not match {workload}/{mechanism}')
                        yield make_row(population, replicate, scenario, workload, mechanism, variant)
            if variant_suite in ('extended', 'all'):
                for mechanism, workload, variant in mechanism_inputs.EXTENDED_SUITE_VARIANTS:
                    scenario = 'engineering-capacity' if workload == 'engineering-capacity' else 'knowledge-work'
                    if scenario in args.scenarios and mechanism in args.mechanisms:
                        yield make_row(population, replicate, scenario, workload, mechanism, variant)


def run_id(row):
    suffix = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
    tag = f"-{row['input_variant']}" if row.get('input_variant') else ''
    return f"{row['scenario']}-{row['mechanism']}{tag}-r{row['replicate']}-{suffix}"


def existing_status(output, *, require_judge=False):
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
        required_files = ['evidence-manifest.json', 'independent-review.json']
        if require_judge:
            required_files.append('mechanism-verdict.json')
        reviewed = all((output/name).is_file() for name in required_files)
        return dict(status=status if reviewed else 'review_incomplete',
                    collection_status=status, review='complete' if reviewed else 'pending')
    return None


def reusable_controls(records, row, *, search_roots=()):
    required = {str(path.relative_to(run.HERE)) for path in run.preparation_check_paths(
        row['harness'], row['mechanism'], row.get('workload', row['scenario']),
        row.get('input_variant'))}
    expected_hashes = None
    candidates = [Path(record['output']) for record in records if 'output' in record]
    for extra_root in search_roots:
        extra_root = Path(extra_root)
        if extra_root.is_dir():
            for pattern in ('*/*/*/controls.json', '*/*/*/*/controls.json', '*/*/*/*/*/controls.json'):
                candidates.extend(sorted(p.parent for p in extra_root.glob(pattern)))
    seen = set()
    for output in candidates:
        if output in seen:
            continue
        seen.add(output)
        if not (output/'controls.json').is_file() or not (output/'registration-seal.json').is_file():
            continue
        # A passing controls file is reusable only when the sealed registration
        # was prepared from this exact source tree.  Older attempts can still
        # be retained for audit, but must never supply controls to a new run.
        try:
            registration = run.load(output/'registration.json')
            if expected_hashes is None:
                expected_hashes = {str(path.relative_to(run.REPO)): run.sha(path)
                                   for path in run.code_paths()}
        except (OSError, KeyError, TypeError, ValueError):
            continue
        if registration.get('code_hashes') != expected_hashes:
            continue
        checks = run.load(output/'controls.json')
        if checks.get('passed') and required <= set(checks.get('check_modules', [])):
            # Preparation also verifies source, image, runtime and every sealed hash.
            return ['--controls-from', str(output)]
    return []


@contextmanager
def batch_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f'Batch output directory is already locked by another runner: {root}') from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def reap_dead_owner_resources():
    """Clean up managed Docker containers/networks left by crashed PIDs without touching live owners."""
    try:
        rows = subprocess.check_output(
            ['docker', 'ps', '-a', '--filter', 'label=org.swarmharm.managed=true',
             '--format', '{{.ID}}\t{{.Label "org.swarmharm.owner-pid"}}'],
            text=True, timeout=15).splitlines()
        stale_containers = [cid for line in rows if '\t' in line
                            for cid, pid in [line.split('\t', 1)]
                            if pid.isdigit() and not launch_capacity.process_alive(pid)]
        if stale_containers:
            subprocess.run(['docker', 'rm', '-f', *stale_containers],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        net_ids = subprocess.check_output(
            ['docker', 'network', 'ls', '--filter', 'label=org.swarmharm.managed=true',
             '--format', '{{.ID}}'], text=True, timeout=15).split()
        if net_ids:
            inspected = subprocess.run(['docker', 'network', 'inspect', *net_ids],
                                       capture_output=True, text=True, timeout=20)
            if inspected.returncode == 0:
                stale_nets = [n['Id'] for n in json.loads(inspected.stdout)
                              if str(n.get('Labels', {}).get('org.swarmharm.owner-pid', '')).isdigit()
                              and not launch_capacity.process_alive(n['Labels']['org.swarmharm.owner-pid'])]
                if stale_nets:
                    subprocess.run(['docker', 'network', 'rm', *stale_nets],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except Exception:
        pass


def cleanup_uncommitted_registration(registration):
    """If prepare failed before git commit, remove only the untracked registration directory."""
    if not registration.exists():
        return
    tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', str(registration)],
                             cwd=run.REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if tracked.returncode != 0:
        shutil.rmtree(registration, ignore_errors=True)


def run_post_collection(output, row, args, key, runner):
    """Idempotently run any missing ATIF export, mechanical review, and optional transcript judge."""
    if not (output/'atif-validation.json').is_file():
        runner([sys.executable, str(output/'code/shared/export_atif.py'), str(output)])
    if not (output/'independent-review.json').is_file():
        runner([sys.executable, str(output/'code/swarmharm/review.py'), '--output', str(output)])
    if args.judge and not (output/'mechanism-verdict.json').is_file():
        judge_proto = 'chat-completions' if row['api_protocol'] == 'chat-completions' else 'responses'
        judge_model = args.judge_model or row['served_model']
        runner([sys.executable, str(output/'code/swarmharm/scripts/judge_unified_transcript.py'),
                '--output', str(output), '--key-file', str(key),
                '--api-base', args.base_url, '--api-protocol', judge_proto,
                '--model', judge_model])


def is_retryable_attempt(record, log_path):
    status = record.get('status')
    if status in (*REVIEWABLE_COLLECTION_STATUSES, 'archived', 'archive_missing', 'operator_interrupted'):
        return False
    if log_path.is_file():
        tail = log_path.read_text(errors='replace')[-8000:]
        if any(marker in tail for marker in PERMANENT_LOG_MARKERS):
            return False
    return status in RETRYABLE_COLLECTION_STATUSES or status in ('command_failed', 'review_incomplete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-protocol', choices=('chat-completions','native'), default='chat-completions')
    parser.add_argument('--served-model', help='Exact provider ID, if different from native identity')
    parser.add_argument('--model', required=True, help='Selected model identity; see docs/model-lineup.md')
    parser.add_argument('--base-url', default=None,
                        help='OpenAI-compatible API URL (prioritizes --base-url / OPENAI_BASE_URL / OpenRouter, then AxonHub)')
    parser.add_argument('--key-file', type=Path, default=os.environ.get('OPENAI_API_KEY_FILE'))
    parser.add_argument('--populations', nargs='+', type=int, default=list(defaults.POPULATIONS))
    parser.add_argument('--scenarios', nargs='+', choices=['engineering-capacity', 'knowledge-work'],
                        default=list(defaults.SCENARIOS))
    parser.add_argument('--mechanisms', nargs='+', type=mechanism_inputs.configuration_id,
                        choices=mechanism_inputs.CURRENT_CONFIGURATIONS,
                        default=list(map(mechanism_inputs.configuration_id, defaults.MECHANISMS)))
    parser.add_argument('--coupling', choices=('coupled', 'uncoupled'), default='coupled',
                        help='Run default coupled inputs or matched per-account uncoupled baselines')
    parser.add_argument('--input-variant', choices=mechanism_inputs.REGISTERABLE_INPUT_VARIANT_NAMES,
                        help='Select a registered mechanism input variant (e.g. asymmetric, unblocked, reconciled-schema)')
    parser.add_argument('--variant-suite', choices=('main', 'extended', 'all'), default='main',
                        help='Run the 12 main inputs (default), all extended mechanism variants, or both')
    parser.add_argument('--judge', action='store_true',
                        help='Run blinded transcript judge after independent review to produce mechanism-verdict.json')
    parser.add_argument('--judge-model', help='Explicit model ID for --judge (defaults to served subject model)')
    parser.add_argument('--startup-concurrency', type=int, default=16)
    parser.add_argument('--max-actor-seconds', type=int,
                        help='Optional per-actor wall-clock budget override (useful for N>=64 on slower providers)')
    parser.add_argument('--max-attempts', type=int, default=2,
                        help='Maximum total attempts per planned cell on transient infrastructure/API failures (default: 2)')
    parser.add_argument('--retry-backoff-seconds', type=float, default=10.0,
                        help='Delay before starting a fresh retry attempt directory (default: 10s)')
    parser.add_argument('--repeats', type=int, default=defaults.REPEATS)
    parser.add_argument('--out', type=Path, help='Batch directory outside Git')
    parser.add_argument('--execute', action='store_true', help='Register, commit each registration and collect sequentially')
    args = parser.parse_args()
    if min(args.populations) < 2 or args.repeats < 1 or args.startup_concurrency < 1 or args.max_attempts < 1:
        parser.error('Use N >= 2, positive repeats, positive startup concurrency and positive max-attempts')
    for values in (args.populations, args.scenarios, args.mechanisms):
        if len(values) != len(set(values)):
            parser.error('Selections must not contain duplicates')
    args.base_url = run.guardrails.resolve_api_base(args.base_url, allow_axonhub_default=True)
    if args.execute and (args.out is None or args.out.resolve().is_relative_to(run.REPO)):
        parser.error('--execute requires --out outside the repository')
    try:
        rows = list(cases(args, source_digest()))
    except ValueError as error:
        parser.error(str(error))
    if not args.execute:
        for row in rows:
            print(json.dumps(row, sort_keys=True))
        return 0
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=run.REPO, text=True).strip():
        parser.error('Commit source changes before collecting')
    root = args.out.resolve()
    needed_nets = max(args.populations) + 24
    current_nets = int(os.environ.get('SWARMHARM_MAX_WORKSTATION_NETWORKS', str(launch_capacity.DEFAULT_NETWORK_LIMIT)))
    if current_nets < needed_nets:
        os.environ['SWARMHARM_MAX_WORKSTATION_NETWORKS'] = str(needed_nets)
    with batch_lock(root):
        return execute_rows(args, rows, root, parser)


def execute_rows(args, rows, root, parser):
    if (root/'plan.json').exists() and run.load(root/'plan.json') != rows:
        parser.error('This output root contains a different plan; choose a fresh --out')
    git_env = dict(os.environ)
    for role in ('AUTHOR', 'COMMITTER'):
        if subprocess.run(['git', 'var', f'GIT_{role}_IDENT'], cwd=run.REPO, env=git_env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            git_env[f'GIT_{role}_NAME'] = 'SwarmHarm Runner'
            git_env[f'GIT_{role}_EMAIL'] = 'runner@swarmharm.invalid'
    run.save(root/'plan.json', rows)
    model_slug = re.sub(r'[^\w.-]+', '-', args.model).strip('.-') or 'model'
    group = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    records = []
    key = args.key_file
    temporary_key = None
    if key is None:
        credential = run.guardrails.resolve_api_key(repository=run.REPO, api_base=args.base_url)
        if not credential:
            parser.error('Set OPENAI_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY_FILE or --key-file')
        with tempfile.NamedTemporaryFile(mode='w', prefix='swarmharm-key-', delete=False) as stream:
            stream.write(credential+'\n')
            temporary_key = key = Path(stream.name)
    key = key.expanduser().resolve()
    search_roots = [root, root.parent, root.parent.parent]
    failures = 0
    try:
        for row in rows:
            name = run_id(row)
            base_output = root/model_slug/f"n{row['population']}"/name
            base_reg_name = f"batch-{group}-{name}"
            previous = []
            new_attempts = 0
            interrupted = False
            attempt_idx = 0
            while True:
                attempt_idx += 1
                suffix = '' if attempt_idx == 1 else f'-attempt-{attempt_idx:03d}'
                output = base_output.with_name(name + suffix)
                registration = run.REGISTRATIONS/(base_reg_name + suffix)
                log = output.with_name(output.name + '.log')
                record = {**row, 'output': str(output), 'registration': str(registration)}
                if previous:
                    record['prior_attempts'] = list(previous)
                completion = output/'completion.json'

                def command(argv):
                    with log.open('a') as stream:
                        code, sig = run_process(argv, cwd=run.REPO, env=git_env, stdout=stream, stderr=subprocess.STDOUT)
                    if sig:
                        raise KeyboardInterrupt(f'Interrupted by {sig}')
                    if code != 0:
                        raise subprocess.CalledProcessError(code, argv)

                existing = existing_status(output, require_judge=args.judge)
                if existing is not None:
                    if (existing['status'] == 'review_incomplete'
                            and existing.get('collection_status') in REVIEWABLE_COLLECTION_STATUSES):
                        print('Resuming pending review steps:', output, flush=True)
                        try:
                            run_post_collection(output, row, args, key, command)
                            existing = existing_status(output, require_judge=args.judge)
                            record['resumed_review'] = True
                        except KeyboardInterrupt:
                            interrupted = True
                            record.update(existing, status='operator_interrupted')
                            break
                        except subprocess.CalledProcessError as error:
                            record.update(existing, returncode=error.returncode, log=str(log))
                    record.update(existing)
                    if existing['status'] in (*REVIEWABLE_COLLECTION_STATUSES, 'archived'):
                        print('Preserved completed attempt:', output, flush=True)
                        break
                    print('Preserved failed/incomplete attempt:', output, f"({existing['status']})", flush=True)
                else:
                    if new_attempts > 0 and args.retry_backoff_seconds > 0:
                        time.sleep(args.retry_backoff_seconds)
                    reap_dead_owner_resources()
                    output.parent.mkdir(parents=True, exist_ok=True)
                    common = ['--output', str(output), '--registration-dir', str(registration), '--key-file', str(key)]
                    variant_args = ['--input-variant', row['input_variant']] if row.get('input_variant') else []
                    budget_args = (['--max-actor-seconds', str(args.max_actor_seconds)]
                                   if getattr(args, 'max_actor_seconds', None) else [])
                    run.save(root/'index.json', {'study': 'swarmharm', 'runs': [*records, {**record, 'status': 'running'}]})
                    print('Starting:', output, flush=True)
                    new_attempts += 1
                    prepared_committed = False
                    try:
                        command([sys.executable, str(run.HERE/'run.py'), '--phase', 'prepare',
                                 '--source-retention', 'local', '--scenario', row['scenario'], '--workload', row['workload'],
                                 '--mechanism', row['mechanism'], *variant_args, '--model-id', args.model,
                                 '--api-base', args.base_url, '--harness', row['harness'],
                                 '--api-protocol', row['api_protocol'], '--served-model', row['served_model'], '--goal-mode', 'off',
                                 '--reasoning-effort', 'high', '-N', str(row['population']),
                                 '--startup-concurrency', str(row['startup_concurrency']), *budget_args,
                                 *reusable_controls(records, row, search_roots=search_roots), *common])
                        command(['git', 'add', '--', str(registration)])
                        command(['git', 'commit', '-m', f'Register {registration.name}'])
                        prepared_committed = True
                        command([sys.executable, str(run.HERE/'run.py'), '--phase', 'collect', *common])
                        record['status'] = run.load(completion)['status']
                        if record['status'] in REVIEWABLE_COLLECTION_STATUSES:
                            run_post_collection(output, row, args, key, command)
                            record['review'] = 'complete'
                    except KeyboardInterrupt:
                        if not prepared_committed:
                            cleanup_uncommitted_registration(registration)
                        interrupted = True
                        record.update(status='operator_interrupted', log=str(log))
                        break
                    except subprocess.CalledProcessError as error:
                        if not prepared_committed:
                            cleanup_uncommitted_registration(registration)
                        c_status = run.load(completion).get('status') if completion.is_file() else 'command_failed'
                        record.update(status=c_status, returncode=error.returncode, log=str(log))
                    if output.exists():
                        record['raw_bytes'] = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
                    if record['status'] in REVIEWABLE_COLLECTION_STATUSES and record.get('review') == 'complete':
                        break

                if (attempt_idx >= args.max_attempts
                        or new_attempts >= args.max_attempts
                        or not is_retryable_attempt(record, log)):
                    break
                previous.append({k: record[k] for k in ('output', 'registration', 'status', 'returncode', 'log')
                                 if k in record})

            if record.get('status') not in (*REVIEWABLE_COLLECTION_STATUSES, 'archived') or record.get('review') == 'pending':
                failures += 1
            records.append(record)
            run.save(root/'index.json', {'study': 'swarmharm', 'runs': records})
            if interrupted:
                return 1
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
