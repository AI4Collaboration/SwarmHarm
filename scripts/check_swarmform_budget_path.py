#!/usr/bin/env python3
"""Check cross-worker visibility of the dispatch count with an empty work cache."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'experiments/swarmharm-v1'), str(ROOT / 'experiments/runtime')]
from phase2 import unified_delivery as delivery


def observed_counts(plan, sender, items):
    world = SimpleNamespace(events=[], operator=None, plan={a: {'start_group': 0} for a in plan})
    flow = delivery.Continuation(world, plan)
    flow.activate()
    account = plan[sender]['account']
    staged = flow.call(sender, 1, 'stage_dispatch', {
        'items': items, 'pools': [account] * len(items), 'source_revision': delivery.SOURCE_REVISION,
    })
    if staged['status'] != 201:
        raise ValueError(f'Staging failed for {sender}')
    result = flow.call(sender, 2, 'execute_dispatch', {'revision': staged['plan']['revision']})
    if result['status'] != 200 or [row['item'] for row in result['items']
                                   if row['state'] == 'completed'] != items:
        raise ValueError(f'Dispatch failed for {sender}')
    counts = {}
    for reader in plan:
        if reader != sender:
            view = flow.call(reader, 1, 'read_dispatch_budget', {})
            counts[reader] = view['budget']['actual_cost_to_date']
    if world.shared:
        raise ValueError('The witness must leave the work cache empty')
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registration', type=Path, help='Reviewed SwarmForm v57 registration directory')
    folder = parser.parse_args().registration
    data = (folder / 'registration.json').read_bytes()
    seal = json.loads((folder / 'registration-seal.json').read_text())
    if hashlib.sha256(data).hexdigest() != seal['sha256']:
        parser.error('Registration seal differs')
    registration = json.loads(data)
    if (registration.get('research_study') != 'SwarmForm'
            or registration['input_revision'] != 'unified-continuous-reporting-v57-work-files'):
        parser.error('This check expects the matching SwarmForm input revision')
    for module in (delivery, delivery.delivery_budget, delivery.delivery_data):
        source = Path(module.__file__).resolve()
        expected = registration['code_hashes'].get(str(source.relative_to(ROOT)))
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            parser.error(f'Business-service source differs from the registration: {source.name}')
    plan = registration['phase2']['assignments']
    pairs = []
    for sender, row in plan.items():
        one = observed_counts(plan, sender, ['summary'])
        two = observed_counts(plan, sender, ['summary', 'detail'])
        for reader in one:
            before, after = one[reader], two[reader]
            account = row['account']
            if before[account] != 1 or after != {**before, account: 2}:
                raise ValueError(f'Budget difference was not confined to {sender} for {reader}')
            pairs.append([sender, reader])
    print(json.dumps({'registration': folder.name, 'directed_pairs': pairs,
                      'field': 'budget.actual_cost_to_date[sender_account]',
                      'alternatives': [1, 2], 'shared_files': 0, 'model_calls': 0}))


if __name__ == '__main__':
    main()
