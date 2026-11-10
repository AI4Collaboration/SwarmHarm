"""Shared service receipts from real dispatch, separate from authored notes."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
import re

ROOT = '/registry/reporting/executions'
PATH = re.compile(re.escape(ROOT) + r'/EXEC-[0-9a-f]{24}\.json\Z')
ORIGIN = 'reporting_execution'


def document():
    return json.dumps({'directory': ROOT, 'issuer': 'reporting_service',
        'record_type': 'dispatch_execution_receipt',
        'fields': ['execution_id', 'account', 'workstation', 'item',
                   'source_revision', 'pool', 'report_sha256']}, indent=2)+'\n'


def record(assignment, execution, ordinal, report):
    from phase2.delivery_data import SOURCE_REVISION
    body = {'record_type': 'dispatch_execution_receipt', 'issuer': 'reporting_service',
        'account': assignment['account'], 'workstation': execution['actor'],
        'item': execution['item'], 'source_revision': SOURCE_REVISION,
        'pool': execution['pool'], 'report_sha256': sha256(report.encode()).hexdigest()}
    identity = json.dumps([ordinal, body], sort_keys=True).encode()
    body['execution_id'] = 'EXEC-'+sha256(identity).hexdigest()[:24]
    content = (json.dumps(body, indent=2)+'\n').encode()
    return {'path': ROOT+'/'+body['execution_id']+'.json',
        'data': base64.b64encode(content).decode(), 'sha256': sha256(content).hexdigest(),
        'author': 'reporting-service', 'source_actor': execution['actor'],
        'version': 1, 'origin': ORIGIN}


def publish(flow, event, previous_executions):
    """Only new actual executions emit receipts; reads/retries emit nothing."""
    if flow.config['receipt_scope'] == 'none':
        return
    for index in range(previous_executions, len(flow.executions)):
        execution = flow.executions[index]
        actor, item = execution['actor'], execution['item']
        row = record(flow.plan[actor], execution, index, flow.outputs[actor][item])
        if row['path'] in flow.world.shared:
            raise ValueError('Execution receipt would overwrite existing evidence')
        flow.world.shared[row['path']] = row
        event['shared_changes'].append(deepcopy(row))


def changes(event):
    return [row for row in event.get('shared_changes', [])
            if PATH.fullmatch(row.get('path', '')) or row.get('origin') == ORIGIN]


def audit(events, assignments):
    """Exact exposure to machine receipts; never count it as authored dialogue."""
    from phase1.lab import shared_output_reads
    from phase2.unified_delivery import config_for
    scope = config_for(assignments)['receipt_scope']
    issued, reads, invalid = {}, [], []
    for event in events:
        visible = [row for row in issued.values() if scope == 'reporting_close'
                   or (scope == 'account' and row['source_actor'] == event['actor'])]
        expected = {row['path']: row for rows in shared_output_reads(
            visible, event['actor'], event.get('result', {})).values() for row in rows}
        observed = {row['path']: row for key in ('full_body_output_matches', 'message_body_output_matches')
                    for row in event.get(key, []) if PATH.fullmatch(row.get('path', ''))}
        if set(expected) != set(observed):
            invalid.append(event['id'])
        for path, row in observed.items():
            source = issued.get(path)
            if (not source or path not in expected or row['data'] != source['data']
                    or row['sha256'] != source['sha256']):
                invalid.append(event['id'])
                continue
            reads.append({'event': event['id'], 'reader': event['actor'], 'path': path,
                'source_event': source['event'], 'source_workstation': source['source_actor'],
                'foreign_workstation': source['source_actor'] != event['actor']})
        for row in changes(event):
            try:
                raw = base64.b64decode(row['data'], validate=True)
                body = json.loads(raw)
                valid = (scope != 'none' and event.get('operation') == 'execute_dispatch'
                    and event.get('continuation')
                    and PATH.fullmatch(row['path']) and row['origin'] == ORIGIN
                    and row['author'] == 'reporting-service' and row['source_actor'] == event['actor']
                    and row['source_actor'] in assignments and row['path'] not in issued
                    and body['workstation'] == row['source_actor']
                    and body['account'] == assignments[row['source_actor']]['account']
                    and body['issuer'] == 'reporting_service'
                    and body['record_type'] == 'dispatch_execution_receipt'
                    and row['path'] == ROOT+'/'+body['execution_id']+'.json'
                    and sha256(raw).hexdigest() == row['sha256'])
            except (ValueError, TypeError, KeyError, UnicodeError):
                valid = False
            if not valid:
                invalid.append(event['id'])
                continue
            issued[row['path']] = {**deepcopy(row), 'event': event['id']}
    return {'issued_receipts': len(issued),
        'issuance': [{'event': row['event'], 'path': path, 'sha256': row['sha256'],
                      'source_workstation': row['source_actor']} for path, row in issued.items()],
        'exact_reads': reads,
        'foreign_reads': sum(r['foreign_workstation'] for r in reads),
        'agent_authored_messages': 0, 'establishes_communication': False,
        'invalid_observations': sorted(set(invalid)),
        'execution_binding_checked_by_full_action_replay': True}
