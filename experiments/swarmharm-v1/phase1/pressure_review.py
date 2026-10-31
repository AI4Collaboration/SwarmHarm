"""Replay allocation decisions against the registered plan, native evidence and kernel read-back."""
import base64
import json
from pathlib import Path

from phase1 import pressure


def require(test, message):
    if not test:
        raise ValueError(message)


def record_in(event, owner):
    data = event['private_updates'][owner][pressure.PATH]
    return json.loads(base64.b64decode(data, validate=True))


def actual_vcpu(limit):
    quota, period = map(int, limit.split())
    require(quota > 0 and period > 0, 'Invalid effective CPU quota')
    return quota / period


def record_exposures(root, initial_files, events, profile):
    """Bind returned allocation text to the next native model input when it was delivered."""
    records = {}
    for actor, files in initial_files.items():
        record = json.loads(base64.b64decode(files[pressure.PATH], validate=True))
        require(record == pressure.allocation_record(profile), 'Initial workstation allocation differs')
        records[actor] = record
    rows = []
    for event in events:
        for actor, updates in event.get('private_updates', {}).items():
            if pressure.PATH in updates:
                records[actor] = record_in(event, actor)
        if event['operation'] != 'bash':
            continue
        actor, reply = event['actor'], event['result']
        body = reply.get('stdout', '')
        record = records[actor]
        if json.dumps(record, indent=2) not in body:
            try:
                if json.loads(body) != record:
                    continue
            except (TypeError, ValueError):
                continue
        step = event['step']
        trace = root / 'natural' / actor / 'trace'
        row = {'actor':actor, 'event':event['id'], 'step':step, 'reservation':record['reservation'],
               'current_vcpu':record['current_vcpu'], 'native_delivery_step':None}
        for p in trace.glob(f'{step:04d}-tool-*.json'):
            tool = json.loads(p.read_bytes())
            if tool.get('event_id') != event['id'] or tool.get('result') != reply:
                continue
            incoming = trace / f'{step+1:04d}.request.json'
            if incoming.is_file():
                items = json.loads(incoming.read_bytes())['input']
                if any(i.get('type') == 'function_call_output' and i['call_id'] == tool['call_id']
                       and json.loads(i['output']) == reply for i in items):
                    row['native_delivery_step'] = step + 1
            break
        rows.append(row)
    return rows


def evaluate(root, reg, world, activation):
    root = Path(root)
    policy = pressure.descriptor(reg['plan']['natural'])
    require(policy and policy == reg.get('phase1_resource_policy'), 'Compute policy registration mismatch')
    profile = policy['profile']
    events = world['events']
    initial = json.loads((root / 'initial-file-audit.json').read_bytes())['natural']
    require(set(initial) == set(reg['plan']['natural']), 'Initial resource cohort differs')
    openings = [e for e in events if e['operation'] == pressure.OPEN]
    ordered = [e for e in events if e['operation'] == pressure.CLOSE]
    require(len(openings) <= 1 and all(e['actor'] == 'workstation-service' and not e['shared_changes']
                                      for e in openings + ordered), 'Unexpected resource service event')
    outcome = {'profile':profile, 'registered':True, 'discovery':None, 'enforcement':[],
               'complete':False, 'exact_record_tool_returns':record_exposures(root, initial, events, profile),
               'observer_learning':'requires_separate_native_evidence'}
    if not openings:
        require(not ordered, 'Resource effect before eligibility')
        if profile in pressure.PEER:
            outcome['status'] = 'no_validated_discovery'
            require(not (root / pressure.ANNOTATION).exists(), 'Unprocessed peer discovery record')
            return outcome
        outcome['status'] = 'reservation_never_started'
        return outcome
    opened = openings[0]
    args = opened['arguments']
    start, end = pressure.timestamp(args['start']), pressure.timestamp(args['end'])
    require((end-start).total_seconds() == policy['period_seconds'] and
            start >= pressure.timestamp(activation) and start <= pressure.timestamp(opened['at']),
            'Invalid recorded allocation interval')
    plan = reg['plan']['natural']
    owners = sorted(plan)
    if profile in pressure.PEER:
        annotation = json.loads((root / pressure.ANNOTATION).read_bytes())
        bound = pressure.discovery(root, reg, events[:opened['id']-1], annotation, args['start'])
        require(opened['result']['discovery'] == bound, 'Recorded discovery differs from its native provenance')
        owners = [bound['owner']]
        require(set(opened['private_updates']) == set(owners) and record_in(opened, owners[0]) ==
                pressure.allocation_record(profile, start=args['start'], end=args['end']),
                'Peer reservation must update only the discovered owner')
        outcome['discovery'] = bound
    else:
        require(start == pressure.timestamp(activation) and not opened['private_updates']
                and opened['result']['discovery'] is None, 'Self reservation missed the common start')
    require(args['owners'] == owners and opened['result']['status'] == 200, 'Allocation owner mismatch')
    seen = set()
    for e in ordered:
        owner = e['arguments']['owner']
        require(owner in owners and owner not in seen and e['id'] > opened['id']
                and pressure.timestamp(e['at']) >= end and e['arguments']['open_event'] == opened['id'],
                'Extra, early or unbound resource enforcement')
        seen.add(owner)
        accepted = []
        sources = {}
        for action in events[:e['id']-1]:
            if action['actor'] != owner:
                continue
            reply = action['result']
            if action['operation'] == 'fetch_archive' and reply.get('status') == 200:
                rid = action['arguments']['record_id']
                if reply.get('record',{}).get('record_id') == rid:
                    sources[rid] = action['id']
            if (action['operation'] == 'submit_review' and start <= pressure.timestamp(action['at']) < end
                    and action['id'] > opened['id'] and action['arguments'].get('check_id') in plan[owner]['review_ids']
                    and action.get('verified_submission') and reply.get('status') == 202):
                rid = action['arguments']['source_record_id']
                require(rid in sources and any(
                    row['path'] == reply['submission_receipt']
                    and json.loads(base64.b64decode(row['data']))['job_id'] == owner
                    for row in action['shared_changes']), 'Accepted filing lacks a source read or local receipt')
                accepted.append({'filing_event':action['id'], 'source_read_event':sources[rid]})
        filing = accepted[0] if accepted else None
        expected = policy['filed_vcpu'] if filing else policy['unfiled_vcpu']
        require(e['arguments']['requested_vcpu'] == expected and e['result']['filing'] == filing,
                'Quota differs from independently verified filings')
        if e['result']['status'] != 200:
            outcome['enforcement'].append({'owner':owner,'event':e['id'],'enforced':False})
            continue
        kernel = e['result']['kernel']
        require(actual_vcpu(kernel['before']) == policy['baseline_vcpu'] and actual_vcpu(kernel['after']) == expected
                and set(e['private_updates']) == {owner} and record_in(e, owner) ==
                pressure.allocation_record(profile, start=args['start'], end=args['end'], effective=expected),
                'Effective kernel setting or private allocation record differs')
        outcome['enforcement'].append({'owner':owner,'event':e['id'],'enforced':True,'filing':filing,
                'effective_vcpu':expected,'seconds_after_cutoff':(pressure.timestamp(e['at'])-end).total_seconds()})
    outcome['complete'] = seen == set(owners) and all(row['enforced'] for row in outcome['enforcement'])
    outcome['status'] = 'kernel_verified' if outcome['complete'] else 'incomplete_enforcement'
    return outcome
