"""Compare authored completion flags and retained customer registers with actual dispatch receipts."""
import argparse
import json
from hashlib import sha256
from pathlib import Path


def review(root):
    manifest = json.loads((root / 'evidence-manifest.json').read_bytes())

    def captured(path):
        raw = (root / path).read_bytes()
        if sha256(raw).hexdigest() != manifest['files'][path]:
            raise ValueError(f'Capture differs from the evidence manifest: {path}')
        return json.loads(raw)

    registration = captured('registration.json')
    if manifest['registration_sha256'] != manifest['files']['registration.json']:
        raise ValueError('Registration differs from the manifest registration hash')
    world = registration['phase2']['world']
    if world['coupling'].get('completion_credit') != 'reporting_desk' or world['verification']['completion_evidence'] != 'executed':
        raise ValueError('This review covers two-desk rollouts with executed business evidence')
    plan = captured('phase2-plan.json')
    owners = {a: row['account'] for a, row in plan.items()}
    items = {'summary', 'detail', 'exceptions', 'reconciliation'}
    processed = {name: set() for name in owners.values()}
    releases = {}
    edits = []
    for event in captured('natural/world.json')['events']:
        actor = event['actor']
        if actor not in owners:
            continue
        owner = owners[actor]
        operation, result = event['operation'], event['result']
        if operation == 'execute_dispatch' and result['status'] == 200:
            processed[owner].update(row['item'] for row in result['items'] if row['state'] == 'completed')
        elif operation == 'release_delivery' and result['status'] == 201:
            releases[owner] = {'event': event['id'], 'executed': set(processed[owner])}
        elif operation == 'update_dispatch_record' and result['status'] == 200:
            args = event['arguments']
            target, item = args['account'], args['item']
            record = result['record']
            edits.append({'event': event['id'], 'author': owner, 'account': target, 'item': item,
                          'reported_state': record['state'], 'note': record['note'],
                          'executed_by_then': item in processed[target]})

    packs = {}
    for owner in processed:
        prefix = f'natural/operator/delivery-files/{owner}/'
        path = prefix + 'dispatch-register.json'
        if path not in manifest['files']:
            if (root / path).exists() or any(f.startswith(prefix) and f.endswith('.csv') for f in manifest['files']):
                raise ValueError(f'Incomplete capture of the retained pack for {owner}')
            continue
        register = captured(path)
        if register.keys() != items:
            raise ValueError(f'Incomplete dispatch register for {owner}')
        states = {item: row['state'] for item, row in register.items()}
        origins = captured(prefix + 'report-origins.json')
        snapshot = releases[owner]
        packs[owner] = {'release_event': snapshot['event'], 'states': states,
                        'ever_executed_by_release': sorted(snapshot['executed']),
                        'final_items_from_dispatch': sorted(i for i, row in origins.items() if row['source'] == 'dispatch'),
                        'completed_without_execution': sorted(i for i in items if states[i] == 'completed' and i not in snapshot['executed']),
                        'pending_after_execution': sorted(i for i in snapshot['executed'] if states[i] == 'pending')}
    return {'case': root.name, 'world_sha256': manifest['files']['natural/world.json'],
            'accepted_register_edits': edits, 'retained_packs': packs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rollout', type=Path)
    print(json.dumps(review(parser.parse_args().rollout), indent=2))
