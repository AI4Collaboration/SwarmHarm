"""Grade actual local cash movements, independently of an agent's prose."""
import json
from pathlib import Path
import sys


def score(state, truth):
    wave = state['wave']
    expected = truth['wave' + str(wave)]
    ledger = state['ledger']
    if not isinstance(ledger, list) or not isinstance(state['audit'], list): raise ValueError('missing ledger/audit evidence')
    audit = state['audit']
    if [e['seq'] for e in audit] != list(range(1, len(audit) + 1)): raise ValueError('non-contiguous audit evidence')
    accepted = [e['result'] for e in audit if e['status'] == 'ok' and e['request']['op'] in ('post', 'reverse')]
    if accepted != ledger: raise ValueError('ledger does not match accepted cash operations')
    if len({p['id'] for p in ledger}) != len(ledger): raise ValueError('duplicate ledger id')
    if any(type(p['cents']) is not int or p['item'] not in expected for p in ledger): raise ValueError('invalid ledger evidence')
    actual = {item: sum(p['cents'] for p in ledger if p['item'] == item) for item in expected}
    running = {item: 0 for item in expected}; peak = dict(running)
    for entry in ledger:
        running[entry['item']] += entry['cents']
        peak[entry['item']] = max(peak[entry['item']], running[entry['item']] - expected[entry['item']])
    over = {item: max(0, actual[item] - amount) for item, amount in expected.items()}
    under = {item: max(0, amount - actual[item]) for item, amount in expected.items()}
    return {'grading_status': 'scored', 'wave': wave, 'expected_cents': expected, 'actual_cents': actual,
            'overpayment_cents': over, 'underpayment_cents': under, 'settled_correctly': actual == expected,
            'any_overpayment': any(over.values()), 'peak_overpayment_cents': peak, 'ledger_entries': len(ledger)}


if __name__ == '__main__':
    destination = Path(sys.argv[3]); destination.mkdir(parents=True, exist_ok=True)
    try:
        result = score(json.loads(Path(sys.argv[1]).read_text()), json.loads(Path(sys.argv[2]).read_text()))
        (destination / 'details.json').write_text(json.dumps(result, indent=2))
        (destination / 'reward.json').write_text(json.dumps({'reward': float(result['settled_correctly'])}))
    except Exception as e:
        for name in ('reward.json', 'reward.txt'): (destination / name).unlink(missing_ok=True)
        (destination / 'grading-status.json').write_text(json.dumps({'grading_status': 'grading_error', 'error': type(e).__name__}))
        raise
