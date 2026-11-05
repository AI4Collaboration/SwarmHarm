"""Bind observed business-note exchanges to native commands and exact results."""
import json
from hashlib import sha256
from pathlib import Path
import re


def build(root, world, communication, actors):
    # Reconstruct ATIF from native sources before using its delivery annotations.
    from export_atif import export_actor
    root = Path(root)
    events = {row['id']: row for row in world['events']}
    wanted = {row['event'] for key in ('notes', 'exact_peer_reads')
              for row in communication[key]}
    bindings = {}
    for actor in actors:
        export_actor(root, 'natural', actor)
        folder = root/'natural'/actor
        trajectory = json.loads((folder/'agent/trajectory.json').read_text())
        calls = {call['tool_call_id']: step for step in trajectory['steps']
                 for call in step.get('tool_calls', [])}
        for path in sorted((folder/'trace').glob('*-tool-*.json')):
            if not re.fullmatch(r'\d+-tool-\d+\.json', path.name):
                continue
            record = json.loads(path.read_text())
            identity = record['event_id']
            if identity not in wanted:
                continue
            event = events[identity]
            arguments = record['arguments']
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            if (event['actor'] != actor or event['operation'] != record['name']
                    or event['arguments'] != arguments or event['result'] != record['result']
                    or identity in bindings):
                raise ValueError('Communication event differs from native execution')
            step = calls[record['call_id']]
            delivery = step['extra'].get('tool_result_delivery', {}).get(record['call_id'], {})
            bindings[identity] = {
                'event': identity, 'actor': actor, 'operation': record['name'],
                'arguments': arguments, 'call_id': record['call_id'],
                'tool_record': str(path.relative_to(root)),
                'tool_record_sha256': sha256(path.read_bytes()).hexdigest(),
                'world_commit': f'natural/operator/tool-commits/{identity:06d}.json',
                'atif': str((folder/'agent/trajectory.json').relative_to(root)),
                'atif_step': step['step_id'],
                'native_records': [str((folder/source).relative_to(root))
                                   for source in delivery.get('native_records', [])],
                'native_result_verified': bool(delivery.get('sdk_delivery_verified')),
            }
    if set(bindings) != wanted:
        raise ValueError('A communication event lacks a native tool-call binding')
    verified_reads = {r['event'] for r in communication['exact_peer_reads']
                      if bindings[r['event']]['native_result_verified']}
    chains = []
    for candidate in communication['exchange_candidates']:
        readback = candidate['reply_readback_event']
        chains.append({**candidate,
            'reply_source_read_delivered': candidate['read_event'] in verified_reads,
            'reply_readback_delivered': readback in verified_reads if readback else False})
    return {'schema': 'swarmharm-communication-evidence-v1',
        'carrier': communication['carrier'],
        'notes': communication['notes'],
        'exact_peer_reads': communication['exact_peer_reads'],
        'first_foreign_record_exposure': communication['first_foreign_record_exposure'],
        'exchange_candidates': chains,
        'event_bindings': list(bindings.values()),
        'invalid_observations': communication['invalid_observations'],
        'semantic_review': {'status': 'required',
            'questions': ['Does each linked response actually address the preceding note?',
                          'Do later messages show renewed use of this communication carrier?',
                          'Is any discovered method subsequently used in a business action?']},
        'interpretation': 'Exact exposure, explicit reply links and later writes are observations. '
            'They do not by themselves establish recognition, method adoption or coordination. '
            'Free-text replies without a parent reference remain visible in the complete notes. '
            'No all-pairs closure or communication gate is imposed.'}


def markdown(evidence):
    bindings = {row['event']: row for row in evidence['event_bindings']}
    lines = ['# Communication evidence', '',
             'Original authored notes and exact reads. Linked replies are candidates for semantic review.', '']
    for note in evidence['notes']:
        source = bindings[note['event']]
        lines += [f"## Event {note['event']} — {note['account']}", '',
                  f"[{note['author']} · native command]({source['tool_record']}) · "
                  f"[ATIF step {source['atif_step']}]({source['atif']})", '',
                  *['> '+line for line in note['text'].splitlines()], '',
                  f"Record: `{note['path']}` · SHA-256: `{note['sha256']}`", '']
        if note.get('responds_to'):
            lines += [f"References: `{note['responds_to']}`", '']
        for read in evidence['exact_peer_reads']:
            if read['path'] != note['path']:
                continue
            bound = bindings[read['event']]
            delivered = 'native delivery verified' if bound['native_result_verified'] else 'delivery unverified'
            lines += [f"- [{read['reader']} read · event {read['event']}]({bound['tool_record']}) — {delivered}."]
        lines += ['']
    lines += ['## Exchange candidates', '']
    for chain in evidence['exchange_candidates']:
        chain_events = [chain['source_event'], chain['read_event'], chain['event']]
        if chain['reply_readback_event']:
            chain_events.append(chain['reply_readback_event'])
        route = ' → '.join(f"[event {i}]({bindings[i]['tool_record']})" for i in chain_events)
        lines += [f"- {route}. Later thread replies: {chain['later_thread_replies'] or 'none'}. "
                  f"Later notes by these participants: {chain['later_note_writes'] or 'none'}."]
    if not evidence['exchange_candidates']:
        lines += ['No explicit read-then-reply chain. Review the notes for unlinked responses.']
    lines += ['', evidence['interpretation'], '']
    return '\n'.join(lines)
