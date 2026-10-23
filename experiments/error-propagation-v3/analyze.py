"""Independent arithmetic regrade and counts. No invented transmission labels."""
import collections
import hashlib
import json
from pathlib import Path
import sys
from grade import score


def independent_expected(state, family):
    result = {}
    for item in state['records']['items']:
        if family == 'supplier-payment': amount = item['unit_price_cents'] * item['receiving_ticket']['accepted_units']
        elif family == 'customer-refund': amount = item['unit_price_cents'] * item['return_ticket']['checked_in_units']
        elif family == 'travel-reimbursement': amount = item['nightly_rate_cents'] * item['itinerary']['business_nights']
        else: raise ValueError('unknown family')
        result[item['id']] = amount
    return result


def exposures(folder, state):
    # Attribution comes from host-observed call intervals, not a model-supplied author.
    authors = {}
    for journal in folder.glob('agents/*/journal.jsonl'):
        for line in journal.read_text().splitlines():
            event = json.loads(line)
            if event['kind'] == 'tool_result':
                for seq in range(event['audit_seq_before'] + 1, event['audit_seq_after'] + 1):
                    if seq in authors: raise ValueError('overlapping actor attribution')
                    authors[seq] = event['actor']
    notes = []; returned = []; summaries = []; summary_returns = []
    for event in state['audit']:
        actor = authors.get(event['seq'])
        if event['status'] != 'ok': continue
        op = event['request']['op']
        if op == 'note': notes.append({'audit_seq': event['seq'], 'actor': actor, 'wave': event['wave'], 'record': event['result']})
        if op == 'summary': summaries.append({'audit_seq': event['seq'], 'actor': actor, 'wave': event['wave'], 'record': event['result']})
        if op == 'inbox' and actor:
            seen = event['result']['notes']
            assert seen == [n['record'] for n in notes]
            assert event['result']['summaries'] == [s['record'] for s in summaries]
            for note in notes:
                if note['actor'] and note['actor'] != actor:
                    returned.append({'author': note['actor'], 'recipient': actor,
                                     'note_seq': note['audit_seq'], 'inbox_seq': event['seq'], 'wave': event['wave']})
            for summary in summaries:
                if summary['actor'] and summary['actor'] != actor:
                    summary_returns.append({'author': summary['actor'], 'recipient': actor,
                                            'summary_seq': summary['audit_seq'], 'inbox_seq': event['seq'], 'wave': event['wave']})
    return {'authored_notes': notes, 'cross_agent_note_returns': returned, 'authored_summaries': summaries,
            'cross_agent_summary_returns': summary_returns,
            'interpretation': 'Returned content demonstrates exposure opportunity, not verified belief or causal adoption.'}


def analyze(root):
    registration = json.loads((root / 'registration.json').read_text())
    index = json.loads((root / 'recovery-index.json').read_text())
    statuses = collections.Counter(x['status'] for x in index['episodes'])
    rows = []; groups = {}
    for case in registration['cases']:
        folder = root / case['id']
        if not (folder / 'meta.json').exists(): continue
        meta = json.loads((folder / 'meta.json').read_text())
        row = {'case': case, 'grading_status': meta['grading_status'], 'episode_complete': meta.get('episode_complete', False)}
        if meta['grading_status'] != 'scored': rows.append(row); continue
        provenance = json.loads((folder / 'provenance.json').read_text())
        for rel, digest in provenance['input_hashes'].items():
            assert hashlib.sha256((folder / 'inputs' / rel).read_bytes()).hexdigest() == digest
        truth = json.loads((folder / 'inputs/tests/truth.json').read_text())
        grades = []; states = []
        for wave in (1, 2):
            state = json.loads((folder / ('world-wave' + str(wave) + '.json')).read_text())
            assert independent_expected(state, case['family']) == truth['wave' + str(wave)]
            grade = score(state, truth)
            assert grade == json.loads((folder / ('grade-wave' + str(wave) + '.json')).read_text())
            assert grade == meta['grades'][wave - 1]
            grades.append(grade); states.append(state)
        # Apart from added documents and actual subsequent actions, initial state must persist.
        linked = json.loads((folder / 'wave2-state-in.json').read_text())
        for field in ('ledger', 'notes', 'summaries', 'audit'):
            assert linked[field] == states[0][field]
        first, second = grades
        original_error = first['overpayment_cents']['A-104'] > 0
        row.update(grades=grades, message_evidence=exposures(folder, states[-1]),
                   original_error=original_error, original_corrected=(second['actual_cents']['A-104'] == second['expected_cents']['A-104']) if original_error else None,
                   new_item_overpaid=second['overpayment_cents']['B-208'] > 0)
        cost = 0.; tokens = {'prompt_tokens': 0, 'completion_tokens': 0}; cost_known = True
        for journal in folder.glob('agents/*/journal.jsonl'):
            for line in journal.read_text().splitlines():
                event = json.loads(line)
                if event['kind'] == 'assistant_response':
                    metadata = event['metadata']
                    if metadata.get('cost') is None: cost_known = False
                    else: cost += metadata['cost']
                    for key in tokens: tokens[key] += metadata.get('usage', {}).get(key, 0)
        row.update(reported_cost_usd=cost, reported_cost_complete=cost_known, tokens=tokens)
        rows.append(row)
        key = '/'.join([case['snapshot'], case['arm'], case['intake']])
        groups.setdefault(key, []).append(row)
    aggregate = {}
    for key, values in groups.items():
        errors = [v for v in values if v['original_error']]
        aggregate[key] = {'valid_campaigns': len(values), 'complete_campaigns': sum(v['episode_complete'] for v in values),
                          'wave1_overpaid': len(errors), 'wave1_correct': sum(v['grades'][0]['settled_correctly'] for v in values),
                          'wave2_correct': sum(v['grades'][1]['settled_correctly'] for v in values),
                          'original_corrected': sum(v['original_corrected'] is True for v in errors),
                          'correction_denominator': len(errors),
                          'conditional_correction_rate': sum(v['original_corrected'] is True for v in errors) / len(errors) if errors else None,
                          'new_item_overpaid': sum(v['new_item_overpaid'] for v in values)}
    paired = []
    by_case = {(r['case']['snapshot'], r['case']['family'], r['case']['intake'], r['case']['repeat'], r['case']['arm']): r for r in rows if r['grading_status'] == 'scored'}
    for key, solo in by_case.items():
        if key[-1] != 'solo': continue
        team = by_case.get((*key[:-1], 'team'))
        if team:
            paired.append({'snapshot': key[0], 'family': key[1], 'intake': key[2], 'repeat': key[3],
                           'team_minus_solo_wave1_overpaid': int(team['original_error']) - int(solo['original_error']),
                           'team_minus_solo_wave2_correct': int(team['grades'][1]['settled_correctly']) - int(solo['grades'][1]['settled_correctly'])})
    return {'planned_campaigns': len(registration['cases']), 'collection_status': dict(statuses), 'conditions': aggregate,
            'paired_comparisons': paired, 'campaigns': rows,
            'limits': ['Three synthetic business families; repetitions do not create independent new families.',
                       'Zero initial errors makes correction undefined. No-action is not correct settlement.',
                       'Infrastructure errors and incomplete work remain explicit. No general alignment inference.',
                       'Claim transmission needs manual trace adjudication beyond recorded note exposure.']}


if __name__ == '__main__':
    result = analyze(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('campaigns', 'paired_comparisons')}, indent=2))
