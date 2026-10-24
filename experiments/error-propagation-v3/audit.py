"""Observe every saved ledger prefix, including capped and infrastructure cases."""
import json
from pathlib import Path

from analyze import independent_expected
from grade import score


def observed_usage(folder):
    counts = {}; wave_tokens = {}; requests = 0; responses = 0
    totals = {'prompt_tokens': 0, 'completion_tokens': 0, 'reported_cost_usd': 0., 'responses_missing_cost': 0}
    for journal in folder.glob('agents/*/journal.jsonl'):
        wave = stage = None
        for line in journal.read_text().splitlines():
            event = json.loads(line)
            if event['kind'] == 'user_added': wave, stage = event['wave'], event['stage']
            elif event['kind'] == 'request_prepared':
                if wave is None: raise ValueError('Request has no registered stage')
                if not 0 < event['body']['max_tokens'] <= 32768: raise ValueError('Per-call token quota exceeded')
                key = (wave, stage); counts[key] = counts.get(key, 0) + 1; requests += 1
            elif event['kind'] == 'assistant_response':
                usage = event['metadata']['usage']; responses += 1
                for key in ('prompt_tokens', 'completion_tokens'):
                    value = usage[key]
                    if type(value) is not int or value < 0: raise ValueError('Invalid token accounting')
                    totals[key] += value
                wave_tokens[wave] = wave_tokens.get(wave, 0) + usage['completion_tokens']
                cost = event['metadata'].get('cost')
                if cost is None: totals['responses_missing_cost'] += 1
                else: totals['reported_cost_usd'] += cost
    if any(n > 40 for n in counts.values()): raise ValueError('Stage call quota exceeded')
    if any(sum(n for (w, _), n in counts.items() if w == wave) > 120 for wave in (1, 2)):
        raise ValueError('Shared wave call quota exceeded')
    if any(n > 131072 for n in wave_tokens.values()): raise ValueError('Shared wave token quota exceeded')
    return dict(totals, requests=requests, saved_responses=responses, unanswered_requests=requests - responses,
                scope='Saved-response usage only; unanswered requests are not zero-cost or zero-token responses.')


def observed_states(folder, case):
    truth = json.loads((folder / 'inputs/tests/truth.json').read_text())
    authors = {}
    for journal in folder.glob('agents/*/journal.jsonl'):
        for line in journal.read_text().splitlines():
            event = json.loads(line)
            if event['kind'] == 'tool_result':
                for seq in range(event['audit_seq_before'] + 1, event['audit_seq_after'] + 1):
                    if seq in authors: raise ValueError('Overlapping tool attribution')
                    authors[seq] = event['actor']
    rows = []
    for path in sorted(folder.glob('world-wave*.json')):
        state = json.loads(path.read_text())
        if independent_expected(state, case['family']) != truth['wave' + str(state['wave'])]:
            raise ValueError('Independent business arithmetic differs from truth')
        actions = [dict(event, actor=authors.get(event['seq'])) for event in state['audit']
                   if event['status'] == 'ok' and isinstance(event['request'], dict)
                   and event['request'].get('op') in ('post', 'reverse')]
        rows.append({'checkpoint': path.name, 'grade': score(state, truth), 'actions': actions,
                     'scope': 'Observed state only. A partial campaign is not a completed two-wave outcome.'})
    return rows


def merge_recoveries(original, replacements):
    """A continuation may replace a held row, never a capped/completed/unknown one."""
    rows = {row['case']['id']: dict(row, source_run=original.name) for row in original.rows}
    for recovery in replacements:
        for row in recovery.rows:
            case_id = row['case']['id']
            source = original.path / case_id
            from durability import pending
            meta = json.loads((source / 'meta.json').read_text())
            if row['case'] != json.loads((source / 'case.json').read_text()): raise ValueError('Recovery case changed')
            if pending(source): raise ValueError('Unknown original cannot be replaced')
            held = meta['grading_status'] == 'unresolved_request_hold' and not meta.get('stages')
            if held and list(source.rglob('journal.jsonl')): raise ValueError('Untouched case contains a journal')
            checkpoint = meta.get('stages') and meta['stages'][-1]['stop'] == 'unresolved_request_hold'
            if not (held or checkpoint): raise ValueError('Cannot replace completed or capped work')
            if checkpoint:
                from durability import hashes
                proof = json.loads((recovery.path / case_id / 'derivation.json').read_text())
                if proof['source_sha256'] != hashes(source): raise ValueError('Continuation source changed')
            if rows[case_id]['source_run'] != original.name: raise ValueError('Duplicate recovery')
            rows[case_id] = dict(row, source_run=recovery.name)
    return list(rows.values())
