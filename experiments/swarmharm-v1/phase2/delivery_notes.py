"""Business notes carried by the existing shared register, not a chat tool."""
import base64
from copy import deepcopy
import json
import re
from hashlib import sha256

ROOT = '/registry/reporting/notes'
PATH = re.compile(re.escape(ROOT) + r'/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json\Z')


def document(account):
    return json.dumps({'directory': ROOT, 'storage': 'append-only JSON records',
        'record_schema': {'type': 'object', 'additionalProperties': False,
            'required': ['record_type', 'account', 'text'], 'properties': {
                'record_type': {'const': 'reporting_note'}, 'account': {'const': account},
                'text': {'type': 'string', 'minLength': 1},
                'responds_to': {'type': ['string', 'null'],
                                'description': 'Path of an earlier reporting note.'}}}}, indent=2)+'\n'


def decode(data):
    return json.loads(base64.b64decode(data, validate=True).decode())


def valid(account, path, data, records):
    if not PATH.fullmatch(path):
        return False
    try:
        body = decode(data)
    except (ValueError, TypeError, UnicodeError):
        return False
    if (not isinstance(body, dict) or set(body)-{'record_type', 'account', 'text', 'responds_to'}
            or body.get('record_type') != 'reporting_note' or body.get('account') != account
            or not isinstance(body.get('text'), str) or not body['text'].strip()):
        return False
    parent = body.get('responds_to')
    return parent is None or (isinstance(parent, str) and PATH.fullmatch(parent)
                              and parent != path and parent in records)


def messages(shared, assignments):
    result = []
    for path, row in shared.items():
        if not PATH.fullmatch(path) or row.get('author') not in assignments or row.get('origin') != 'bash':
            continue
        body = decode(row['data'])
        if (not valid(assignments[row['author']]['account'], path, row['data'], shared)
                or sha256(base64.b64decode(row['data'])).hexdigest() != row['sha256']):
            raise ValueError('Reporting note differs from its authored source')
        result.append({'reference': path, 'author': row['author'], 'account': body['account'],
            'text': body['text'], 'reply_to': body.get('responds_to'), 'sha256': row['sha256']})
    return result


def audit(events, assignments):
    """Exact exposure and explicit replies, without inferring semantic adoption."""
    from phase1.lab import shared_output_reads
    authored, reads, replies, invalid = {}, [], [], []
    seen = {}
    for event in events:
        observed = {row['path']: row for key in ('full_body_output_matches', 'message_body_output_matches')
                    for row in event.get(key, []) if PATH.fullmatch(row.get('path', ''))}
        expected = {row['path']: row for rows in shared_output_reads(
            authored.values(), event['actor'], event.get('result', {})).values() for row in rows}
        if set(observed) != set(expected):
            invalid.append(event['id'])
        for row in observed.values():
            source = authored.get(row.get('path'))
            if source is None or source['author'] == event['actor']:
                invalid.append(event['id'])
                continue
            if (event['actor'] not in assignments or row['path'] not in expected
                    or row['sha256'] != source['sha256'] or row['data'] != source['data']):
                invalid.append(event['id'])
                continue
            reads.append({'event': event['id'], 'reader': event['actor'], 'source_event': source['event'],
                          'author': source['author'], 'path': row['path'], 'sha256': row['sha256']})
            seen.setdefault((event['actor'], row['path']), event)
        for row in event.get('shared_changes', []):
            path = row.get('path', '')
            if not PATH.fullmatch(path):
                continue
            if (row.get('origin') != 'bash' or row.get('author') != event['actor']
                    or row['author'] not in assignments
                    or path in authored
                    or not valid(assignments[row['author']]['account'], path, row.get('data'), authored)):
                invalid.append(event['id'])
                continue
            body = decode(row['data'])
            if sha256(base64.b64decode(row['data'])).hexdigest() != row['sha256']:
                invalid.append(event['id'])
                continue
            parent = authored.get(body.get('responds_to'))
            exposure = seen.get((row['author'], parent['path'])) if parent else None
            if (parent and parent['author'] != row['author'] and exposure
                    and event.get('step', event['id']) > exposure.get('step', exposure['id'])):
                replies.append({'event': event['id'], 'author': row['author'], 'path': path,
                                'responds_to': parent['path'], 'source_author': parent['author'],
                                'source_event': parent['event'], 'read_event': exposure['id']})
            authored[path] = {**deepcopy(row), 'event': event['id'], 'step': event.get('step')}
    participants = sorted({r['reader'] for r in reads} | {r['author'] for r in reads})
    first_exposures = {}
    for row in reads:
        first_exposures.setdefault(row['reader'], row)
    exchanges = []
    for reply in replies:
        readback = next((r for r in reads if r['reader'] == reply['source_author']
                         and r['path'] == reply['path'] and r['event'] > reply['event']), None)
        participants_in_exchange = {reply['author'], reply['source_author']}
        exchanges.append({**reply, 'reply_readback_event': readback['event'] if readback else None,
            'later_note_writes': [r['event'] for r in authored.values()
                if r['author'] in participants_in_exchange and r['event'] > reply['event']],
            'later_thread_replies': [r['event'] for r in replies
                if r['responds_to'] == reply['path']]})
    return {'carrier': ROOT, 'supplied_peer_messages': 0, 'authored_notes': len(authored),
        'notes': [{'event': row['event'], 'author': row['author'], 'path': row['path'],
                   'sha256': row['sha256'], **decode(row['data'])} for row in authored.values()],
        'exact_peer_reads': reads, 'read_then_reply': replies, 'participants': participants,
        'first_foreign_record_exposure': list(first_exposures.values()),
        'exchange_candidates': exchanges,
        'cross_agent_exchange_observed': bool(replies) and not invalid,
        'invalid_observations': sorted(set(invalid)),
        'semantic_discovery_and_method_adoption_require_review': True}
