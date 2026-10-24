"""Live independent agent contexts, shared office and connected settlement waves."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'back-office-v1'))
import run_model as native
from durability import append, atomic_bytes, export, hashes, pending, save
from design import SYSTEM, advance, instruction
from grade import score
from transport import DurableChat
native.Chat = DurableChat

MODELS = {'old': 'deepseek/deepseek-v4-flash-0731', 'new': 'deepseek/deepseek-v4.1-flash-1017'}
INDEX_LOCK = threading.Lock()


def read_state(ctr):
    return json.loads(native.sh('docker', 'exec', ctr, 'cat', '/var/lib/office/state.json').stdout)


def snapshot(ctr, path):
    state = read_state(ctr); save(path, state); return state


def stage(chat, ctr, messages, work_order, folder, agent, wave, stage_index, budget, *, resume=False):
    journal = folder / 'journal.jsonl'; chat.journal = journal
    if not messages:
        messages.append({'role': 'system', 'content': SYSTEM})
        append(journal, {'kind': 'episode_started', 'messages': list(messages)})
    if resume:
        assert not pending(folder), 'Unknown requests cannot be resumed'
    else:
        messages.append({'role': 'user', 'content': work_order})
        append(journal, {'kind': 'user_added', 'message': messages[-1], 'wave': wave, 'stage': stage_index, 'time': time.time()})
    save(folder / 'messages.json', messages)
    started = time.monotonic()
    stop = 'max_turns'
    stage_calls_remaining = budget.get('stage_calls_remaining', 40)
    if type(stage_calls_remaining) is not int or not 0 <= stage_calls_remaining <= 40:
        raise ValueError('Invalid remaining stage quota')
    stage_calls_used = 40 - stage_calls_remaining
    for turn in range(40 - stage_calls_remaining, 40):
        if budget.get("calls_remaining", 120) <= 0: stop = "wave_call_budget"; break
        if native.UNRESOLVED.is_set(): stop = 'unresolved_request_hold'; break
        if time.monotonic() > budget.get('deadline', started + 7200): stop = 'wall_clock'; break
        if budget['remaining'] < 1024: stop = 'token_budget'; break
        chat.body['max_tokens'] = min(32768, budget['remaining'])
        chat.deadline = budget.get('deadline', started + 7200)
        budget['calls_remaining'] = budget.get('calls_remaining', 120) - 1
        stage_calls_used += 1
        try:
            msg, metadata = chat(messages)
        except Exception as e:
            append(journal, {'kind': 'api_error', 'error': str(e), 'wave': wave, 'stage': stage_index})
            if pending(folder): native.UNRESOLVED.set()
            return 'api_error'
        append(journal, {'kind': 'assistant_response', 'message': msg, 'metadata': metadata,
                         'wave': wave, 'stage': stage_index, 'turn': turn, 'agent': agent})
        usage = metadata.get('usage', {}).get('completion_tokens')
        if type(usage) is not int or usage < 0 or usage > chat.body['max_tokens']:
            native.UNRESOLVED.set()
            append(journal, {'kind': 'budget_accounting_error', 'metadata': metadata})
            return 'budget_accounting_error'
        budget['remaining'] -= usage
        kept = {'role': 'assistant', 'content': msg.get('content')}
        if msg.get('tool_calls'): kept['tool_calls'] = msg['tool_calls']
        if msg.get('reasoning_details'): kept['reasoning_details'] = msg['reasoning_details']
        messages.append(kept)
        append(journal, {'kind': 'assistant_kept', 'wave': wave, 'stage': stage_index})
        save(folder / 'messages.json', messages)
        if not msg.get('tool_calls'):
            stop = 'final_answer' if metadata.get('finish_reason') == 'stop' else 'truncated_response'
            break
        for call in msg['tool_calls']:
            seconds_left = budget.get('deadline', started + 7200) - time.monotonic()
            if seconds_left <= 0:
                stop = 'wall_clock'; break
            before = read_state(ctr)
            append(journal, {'kind': 'tool_prepared', 'call': call, 'wave': wave, 'stage': stage_index})
            try:
                args = json.loads(call['function']['arguments'])
                if call['function']['name'] != 'bash' or not isinstance(args, dict) or not isinstance(args.get('command'), str):
                    raise ValueError('invalid bash command')
                result = native.bash(ctr, args['command'], timeout=min(60, seconds_left))
            except (ValueError, TypeError, KeyError) as e:
                result = {'exit_code': 2, 'stdout': '', 'stderr': str(e)}
            after = snapshot(ctr, folder / ('world-after-' + str(wave) + '-' + str(stage_index) + '-' + str(turn) + '-' + hashlib.sha256(call['id'].encode()).hexdigest()[:10] + '.json'))
            append(journal, {'kind': 'tool_result', 'call_id': call['id'], 'result': result,
                             'wave': wave, 'stage': stage_index, 'actor': agent,
                             'audit_seq_before': len(before['audit']), 'audit_seq_after': len(after['audit'])})
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
            save(folder / 'messages.json', messages)
            export(folder, BACKUP / CURRENT.campaign / 'agents' / agent)
        if stop == 'wall_clock': break
        if metadata.get('finish_reason') == 'length': stop = 'truncated_response'; break
    append(journal, {'kind': 'stage_ended', 'wave': wave, 'stage': stage_index, 'stop': stop,
                     'remaining_wave_completion_tokens': budget['remaining'], 'remaining_wave_calls': budget.get('calls_remaining'),
                     'remaining_stage_calls': 40 - stage_calls_used,
                     'remaining_wave_seconds': max(0, budget.get('deadline', started + 7200) - time.monotonic()), 'time': time.time()})
    return stop


# Each worker has its own campaign pointer; no shared model histories or state.
CURRENT = threading.local()
BACKUP = None


def collect(case, root, task_root, index):
    campaign_id = case['id']; CURRENT.campaign = campaign_id
    folder = root / campaign_id; folder.mkdir(parents=True, exist_ok=False)
    ctr = None
    def status(value, **fields):
        with INDEX_LOCK:
            index[campaign_id].update(status=value, **fields)
            save(root / 'recovery-index.json', {'episodes': list(index.values()), 'backup_locations': [str(BACKUP)],
                 'host': os.uname().nodename, 'instance_id': 'local-docker-live-propagation',
                 'cloud_backup': 'not configured', 'recovery_rule': 'Preserve unknown requests. No retry or process interruption.'})
    status('running')
    save(folder / 'case.json', case)
    task = task_root / case['family'] / case['intake']
    shutil.copytree(task, folder / 'inputs')
    task = folder / 'inputs'
    save(folder / 'provenance.json', {'case': case, 'input_hashes': hashes(task),
         'code_commit': native.sh('git', '-C', str(HERE.parents[1]), 'rev-parse', 'HEAD').stdout.strip(),
         'runner_hashes': hashes(HERE), 'provider': 'novita/fp8', 'model': MODELS[case['snapshot']],
         'reasoning_effort': 'max', 'wave_completion_token_cap': 131072, 'max_tokens_per_call': 32768,
         'stage_max_calls': 40, 'wave_max_calls': 120, 'stages_per_wave': 3, 'waves': 2, 'temperature': None})
    histories = {}; stages = []; grades = []
    try:
        if native.UNRESOLVED.is_set():
            save(folder / 'meta.json', {'grading_status': 'unresolved_request_hold', 'grades': [], 'stages': [], 'unresolved_requests': []})
            export(folder, BACKUP / campaign_id); status('complete', grading_status='unresolved_request_hold'); return
        image = native.image_for(task)
        image_id = native.sh('docker', 'image', 'inspect', '--format', '{{.Id}}', image).stdout.strip()
        save(folder / 'image.json', {'tag': image, 'id': image_id})
        ctr = native.sh('docker', 'run', '-d', '--network', 'none', '--cpus', '1', '--memory', '256m', image, 'sleep', 'infinity').stdout.strip()
        status('running', container=ctr)
        # Operational readiness only, never a model request retry.
        for attempt in range(50):
            ready = native.sh('docker', 'exec', '-u', '65534', ctr, 'office', 'overview', check=False)
            if ready.returncode == 0: break
            time.sleep(.1)
        else: raise RuntimeError('office startup failed')
        snapshot(ctr, folder / 'world-initial.json')
        valid = True; failure_status = None
        for wave in (1, 2):
            if wave == 2:
                assert len(stages) == 3 and all(s['stop'] == 'final_answer' for s in stages), 'unfinished wave must never advance'
                before = read_state(ctr)
                after = advance(before, json.loads((task / 'second-wave.json').read_text()))
                save(folder / 'wave2-state-in.json', after)
                native.sh('docker', 'cp', str(folder / 'wave2-state-in.json'), ctr + ':/var/lib/office/state.json')
                native.sh('docker', 'exec', ctr, 'chmod', '600', '/var/lib/office/state.json')
                append(folder / 'campaign.jsonl', {'kind': 'connected_wave_advanced', 'wave': 2,
                       'preserved_ledger': after['ledger'], 'preserved_notes': after['notes'], 'preserved_summaries': after['summaries']})
            budget = {'remaining': 131072, 'calls_remaining': 120, 'deadline': time.monotonic() + 7200}
            for stage_index in range(3):
                agent = 'solo' if case['arm'] == 'solo' else ('preparer', 'reviewer', 'settler')[stage_index]
                agent_folder = folder / 'agents' / agent; agent_folder.mkdir(parents=True, exist_ok=True)
                messages = histories.setdefault(agent, [])
                chat = native.Chat(MODELS[case['snapshot']], 'novita/fp8', max_tokens=32768, reasoning_effort='max', timeout=600)
                stop = stage(chat, ctr, messages, instruction(stage_index, wave, case['arm']), agent_folder,
                             agent, wave, stage_index, budget)
                stages.append({'wave': wave, 'stage': stage_index, 'agent': agent, 'stop': stop})
                save(folder / 'stages.json', stages)
                export(agent_folder, BACKUP / campaign_id / 'agents' / agent)
                if stop != 'final_answer':
                    failure_status = 'unscored_infrastructure_error' if stop in ('api_error', 'budget_accounting_error', 'unresolved_request_hold') else 'incomplete_stage'
                    valid = False; break
            state = snapshot(ctr, folder / ('world-wave' + str(wave) + '.json'))
            if valid:
                try: grade = score(state, json.loads((task / 'tests/truth.json').read_text()))
                except Exception as e:
                    grade = {'grading_status': 'grading_error', 'error': type(e).__name__}; valid = False; failure_status = 'grading_error'
            elif stop in ('api_error', 'budget_accounting_error', 'unresolved_request_hold'):
                grade = {'grading_status': 'unscored_infrastructure_error'}
            else:
                grade = score(state, json.loads((task / 'tests/truth.json').read_text()))
                grade['completion_status'] = 'incomplete_stage'
            grades.append(grade); save(folder / ('grade-wave' + str(wave) + '.json'), grade)
            if not valid: break
        completed = len(stages) == 6 and all(s['stop'] == 'final_answer' for s in stages)
        meta = {'grading_status': 'scored' if valid else failure_status,
                'episode_complete': completed, 'stages': stages, 'grades': grades,
                'unresolved_requests': pending(folder), 'container': ctr,
                'note': 'Incomplete agent work is reported separately even when business state can be scored.'}
        for agent in histories:
            assigned = [s for s in stages if s['agent'] == agent]
            save(folder / 'agents' / agent / 'meta.json', {
                'model': MODELS[case['snapshot']], 'stop': assigned[-1]['stop'],
                'grading_status': meta['grading_status'], 'score_scope': 'campaign business state, not individual agent credit',
                'episode_complete': all(s['stop'] == 'final_answer' for s in assigned),
                'unresolved_api_requests': pending(folder / 'agents' / agent), 'assigned_stages': assigned})
        save(folder / 'meta.json', meta)
        export(folder, BACKUP / campaign_id)
        # Keep this study's live office available for recovery. No process stop is implied by completion.
        status('complete', grading_status=meta['grading_status'], episode_complete=completed,
               unresolved_requests=meta['unresolved_requests'], container=ctr)
        print(json.dumps({'campaign': campaign_id, 'complete': completed, 'grades': grades}), flush=True)
    except Exception as e:
        native.UNRESOLVED.set()
        save(folder / 'recovery-required.json', {'error': type(e).__name__, 'detail': str(e), 'container': ctr, 'unresolved_requests': pending(folder)})
        status('recovery_required', error=type(e).__name__, container=ctr)
        raise


def main():
    global BACKUP
    parser = argparse.ArgumentParser()
    parser.add_argument('--registration', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    root = args.out.resolve(); BACKUP = args.backup.resolve()
    if root == BACKUP or root in BACKUP.parents or BACKUP in root.parents: raise ValueError('backup must be disjoint')
    root.mkdir(parents=True, exist_ok=False); BACKUP.mkdir(parents=True, exist_ok=False)
    registration = json.loads(args.registration.read_text())
    assert hashes(HERE) == registration['runner_hashes'], 'runner changed since registration'
    for name, digest in registration['native_dependency_hashes'].items():
        assert hashlib.sha256((HERE.parent / 'back-office-v1' / name).read_bytes()).hexdigest() == digest
    assert native.sh('git', '-C', str(HERE.parents[1]), 'rev-parse', 'HEAD').stdout.strip() == registration['code_commit']
    shutil.copytree(HERE, root / 'runner-source' / 'error-propagation-v3', ignore=shutil.ignore_patterns('__pycache__'))
    for name in registration['native_dependency_hashes']:
        destination = root / 'runner-source' / 'back-office-v1' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE.parent / 'back-office-v1' / name, destination)
    task_root = Path(registration['task_root'])
    assert hashes(task_root) == registration['task_hashes'], 'tasks changed since registration'
    save(root / 'registration.json', registration)
    cases = list(registration['cases']); random.Random(registration['schedule_seed']).shuffle(cases)
    save(root / 'dispatch-order.json', [c['id'] for c in cases])
    index = {c['id']: {'id': c['id'], 'dir': c['id'], 'status': 'pending'} for c in cases}
    save(root / 'recovery-index.json', {'episodes': list(index.values())})
    export(root, BACKUP)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(collect, c, root, task_root, index) for c in cases]
        errors = []
        for future in futures:
            try: future.result()
            except Exception as e: errors.append(type(e).__name__)
    save(root / 'completion.json', {'campaigns': len(cases), 'errors': errors, 'unresolved_requests': pending(root)})
    export(root, BACKUP)
    if errors or pending(root): raise SystemExit(1)


if __name__ == '__main__': main()
