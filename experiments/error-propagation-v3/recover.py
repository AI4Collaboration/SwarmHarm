"""Audit held work and derive a continuation without changing source evidence."""
import copy
import json
from pathlib import Path
import shutil
import time

import run
from durability import append, export, hashes, pending, save


def untouched(source):
    registration = json.loads((source / 'registration.json').read_text())
    selected = []
    for case in registration['cases']:
        folder = source / case['id']
        meta = json.loads((folder / 'meta.json').read_text())
        if meta['grading_status'] == 'unresolved_request_hold' and not meta.get('stages'):
            if list(folder.rglob('journal.jsonl')) or pending(folder):
                raise ValueError('Held case has request evidence; manual reconciliation required')
            selected.append(case)
    return selected


def held_stage(source):
    """Return remaining quotas only at a fully committed request/tool boundary."""
    if pending(source):
        raise ValueError('Unknown request cannot be resumed')
    meta = json.loads((source / 'meta.json').read_text())
    stages = meta['stages']
    if not stages or stages[-1]['stop'] != 'unresolved_request_hold':
        raise ValueError('Only a pre-request hold can be resumed')
    if any(s['stop'] != 'final_answer' for s in stages[:-1]):
        raise ValueError('Earlier stage is unfinished')
    last = stages[-1]
    if last['agent'] != 'solo':
        raise ValueError('Team continuation needs a shared-wave quota reconstruction; not supported by this bounded recovery')
    folder = source / 'agents' / last['agent']
    events = [json.loads(line) for line in (folder / 'journal.jsonl').read_text().splitlines()]
    start = max(i for i, e in enumerate(events) if e['kind'] == 'user_added')
    prepared = [e['call']['id'] for e in events if e['kind'] == 'tool_prepared']
    finished = [e['call_id'] for e in events if e['kind'] == 'tool_result']
    if prepared != finished: raise ValueError('Unfinished tool action cannot be replayed')
    messages = json.loads((folder / 'messages.json').read_text())
    order = run.instruction(last['stage'], last['wave'], 'solo' if last['agent'] == 'solo' else 'team')
    if events[start]['message'] != {'role': 'user', 'content': order}:
        raise ValueError('Saved work order does not match the registered stage')
    expected = []; assistant = None
    for event in events:
        if event['kind'] == 'episode_started': expected = list(event['messages'])
        elif event['kind'] == 'user_added': expected.append(event['message'])
        elif event['kind'] == 'request_prepared':
            if event['body']['messages'] != expected: raise ValueError('Request continuity mismatch')
        elif event['kind'] == 'assistant_response': assistant = event['message']
        elif event['kind'] == 'assistant_kept':
            kept = {k: assistant[k] for k in ('role', 'content', 'tool_calls', 'reasoning_details') if k in assistant}
            expected.append(kept)
        elif event['kind'] == 'tool_result':
            expected.append({'role': 'tool', 'tool_call_id': event['call_id'], 'content': json.dumps(event['result'])})
    if expected != messages: raise ValueError('Saved history is not fully committed')
    stage_calls = sum(e['kind'] == 'request_prepared' for e in events[start + 1:])
    if stage_calls >= 40: raise ValueError('Registered stage cap already exhausted')
    calls = []; used = 0; wave = None
    for event in events:
        if event['kind'] == 'user_added': wave = event['wave']
        if wave == last['wave'] and event['kind'] == 'request_prepared': calls.append(event)
        if wave == last['wave'] and event['kind'] == 'assistant_response': used += event['metadata']['usage']['completion_tokens']
    if not calls: raise ValueError('No earlier wave timing evidence')
    elapsed = max(0, (source / 'meta.json').stat().st_mtime - calls[0]['time'])
    budget = {'remaining': 131072 - used, 'calls_remaining': 120 - len(calls), 'stage_calls_remaining': 40 - stage_calls,
              'remaining_seconds': max(0, 7200 - elapsed)}
    return last, messages, budget


def continue_held(source, out, backup):
    source, out, backup = source.resolve(), out.resolve(), backup.resolve()
    for a, b in ((source, out), (source, backup), (out, backup)):
        if a == b or a in b.parents or b in a.parents: raise ValueError('Source, continuation and backup must be disjoint')
    if out.exists() or backup.exists(): raise ValueError('Never reuse a continuation or backup directory')
    last, messages, budget = held_stage(source)
    if last['wave'] != 2 or last['stage'] != 2:
        raise ValueError('Only the final solo stage is supported; later roles/waves must never be invented')
    before = hashes(source)
    out.mkdir(parents=True, exist_ok=False)
    case = json.loads((source / 'case.json').read_text())
    folder = out / case['id']
    shutil.copytree(source, folder, ignore=shutil.ignore_patterns('artifact-manifest.json'))
    # Paths in this derived journal point at exact copied bytes; originals stay untouched.
    for journal in folder.glob('agents/*/journal.jsonl'):
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        for event in events:
            for key in ('path', 'stream_path', 'partial_stream'):
                if event.get(key):
                    event[key] = str(folder / Path(event[key]).relative_to(source))
        journal.write_text(''.join(json.dumps(e) + '\n' for e in events))
    original_meta = json.loads((source / 'meta.json').read_text())
    assert len(original_meta['stages']) == 6
    save(folder / 'derivation.json', {'source_sha256': before, 'original_meta': original_meta,
         'rule': 'Resume only at a fully committed boundary; no provider request or tool action is replayed.',
         'remaining_budget': budget, 'timing': 'Conservative original wall time deducted; recovery pause excluded.'})
    state = json.loads((source / ('world-wave' + str(last['wave']) + '.json')).read_text())
    assert run.read_state(original_meta['container']) == state, 'Live original state changed'
    staging = out / 'workspace-snapshot'; staging.mkdir()
    run.native.sh('docker', 'cp', original_meta['container'] + ':/workspace/.', str(staging))
    image = json.loads((source / 'image.json').read_text())['id']
    ctr = run.native.sh('docker', 'run', '-d', '--network', 'none', '--cpus', '1', '--memory', '256m', image, 'sleep', 'infinity').stdout.strip()
    for _ in range(50):
        if run.native.sh('docker', 'exec', '-u', '65534', ctr, 'office', 'overview', check=False).returncode == 0: break
        time.sleep(.1)
    else: raise RuntimeError('Continuation office not ready; no model request sent')
    run.native.sh('docker', 'cp', str(staging) + '/.', ctr + ':/workspace')
    run.native.sh('docker', 'cp', str(source / ('world-wave' + str(last['wave']) + '.json')), ctr + ':/var/lib/office/state.json')
    run.native.sh('docker', 'exec', ctr, 'chmod', '600', '/var/lib/office/state.json')
    assert run.read_state(ctr) == state
    agent_folder = folder / 'agents' / last['agent']
    append(agent_folder / 'journal.jsonl', {'kind': 'recovery_continued', 'source': str(source), 'time': time.time(), 'remaining_budget': budget})
    run.BACKUP = backup; run.CURRENT.campaign = case['id']
    chat = run.native.Chat(run.MODELS[case['snapshot']], 'novita/fp8', max_tokens=32768, reasoning_effort='max', timeout=600)
    budget['deadline'] = time.monotonic() + budget.pop('remaining_seconds')
    stop = run.stage(chat, ctr, messages, run.instruction(last['stage'], last['wave'], case['arm']), agent_folder,
                     last['agent'], last['wave'], last['stage'], budget, resume=True)
    stages = copy.deepcopy(original_meta['stages']); stages[-1]['stop'] = stop
    save(folder / 'stages.json', stages)
    state = run.snapshot(ctr, folder / 'world-wave2.json')
    grade = run.score(state, json.loads((folder / 'inputs/tests/truth.json').read_text()))
    save(folder / 'grade-wave2.json', grade)
    meta = dict(original_meta, stages=stages, grades=[original_meta['grades'][0], grade], container=ctr,
                episode_complete=stop == 'final_answer', grading_status='scored' if stop == 'final_answer' else 'incomplete_stage',
                unresolved_requests=pending(folder))
    if meta['unresolved_requests']: meta['grading_status'] = 'unscored_infrastructure_error'
    if stop in ('api_error', 'budget_accounting_error', 'unresolved_request_hold'): meta['grading_status'] = 'unscored_infrastructure_error'
    save(folder / 'meta.json', meta)
    save(agent_folder / 'meta.json', {'model': run.MODELS[case['snapshot']], 'stop': stop, 'grading_status': meta['grading_status'],
         'episode_complete': meta['episode_complete'], 'unresolved_api_requests': pending(agent_folder), 'assigned_stages': stages})
    registration = json.loads((source.parent / 'registration.json').read_text()); registration['cases'] = [case]
    save(out / 'registration.json', registration)
    save(out / 'recovery-index.json', {'episodes': [{'id': case['id'], 'dir': case['id'], 'status': 'complete'}]})
    assert hashes(source) == before, 'Original evidence changed'
    export(out, backup)
    return meta


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'continue-held'])
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if args.action == 'plan':
        print(json.dumps({'untouched_cases': [c['id'] for c in untouched(args.source.resolve())],
                          'unresolved_request_ids': [r['request_id'] for r in pending(args.source)]}, indent=2))
    else:
        if args.out is None or args.backup is None: parser.error('Continuation requires new --out and disjoint --backup')
        if args.out.exists() or args.backup.exists(): parser.error('Never reuse a previous continuation directory')
        result = continue_held(args.source.resolve(), args.out.resolve(), args.backup.resolve())
        print(json.dumps({k: result[k] for k in ('grading_status', 'episode_complete')}))
