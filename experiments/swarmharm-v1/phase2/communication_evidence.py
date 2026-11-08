"""Bind observed business-note exchanges to native commands and exact results."""
import json
from hashlib import sha256
from pathlib import Path
import re


def following_result_inputs(folder, records):
    """Find the first later request record carrying each exact tool result."""
    pending = {}
    for path, record in records:
        group = int(path.name.split('-')[0])
        if record['call_id'] in pending:
            raise ValueError('A native tool call ID was reused in the same session')
        pending[record['call_id']] = (group, json.dumps(record['result'], ensure_ascii=False))
    found = {}
    for path in sorted((folder / 'trace').glob('[0-9][0-9][0-9][0-9].request.json')):
        if not pending:
            break
        group = int(path.name.split('.')[0])
        for item in json.loads(path.read_text())['input']:
            identity = item.get('call_id')
            if item.get('type') != 'function_call_output' or identity not in pending:
                continue
            execution, expected = pending[identity]
            if group > execution and item.get('output') == expected:
                found[identity] = path
                del pending[identity]
    return found


def build(root, world, communication, actors):
    # Reconstruct ATIF from native sources before using its delivery annotations.
    from export_atif import export_actor
    root = Path(root)
    harness = json.loads((root/'registration.json').read_text())['harness']['kind']
    events = {row['id']: row for row in world['events']}
    wanted = {row['event'] for key in ('notes', 'exact_peer_reads')
              for row in communication[key]}
    receipts = communication.get('service_receipts', {})
    wanted.update(row['event'] for key in ('issuance', 'exact_reads') for row in receipts.get(key, []))
    bindings = {}
    for actor in actors:
        export_actor(root, 'natural', actor)
        folder = root/'natural'/actor
        trajectory = json.loads((folder/'agent/trajectory.json').read_text())
        calls = {call['tool_call_id']: step for step in trajectory['steps']
                 for call in step.get('tool_calls', [])}
        relevant = []
        for path in sorted((folder/'trace').glob('*-tool-*.json')):
            if not re.fullmatch(r'\d+-tool-\d+\.json', path.name):
                continue
            record = json.loads(path.read_text())
            if record['event_id'] in wanted:
                relevant.append((path, record))
        subsequent = following_result_inputs(folder, relevant)
        for path, record in relevant:
            identity = record['event_id']
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
            later = subsequent.get(record['call_id'])
            native_verified = delivery.get('sdk_delivery_verified') is True
            later_source = str(later.relative_to(root)) if later else None
            native_records = [str((folder/source).relative_to(root)) for source in delivery.get('native_records', [])]
            if harness == 'pi-sdk':
                # Pi records the provider request directly and has no SDK delivery annotation.
                native_verified = later is not None
                native_records = [later_source] if later else []
            bindings[identity] = {
                'event': identity, 'actor': actor, 'operation': record['name'],
                'arguments': arguments, 'call_id': record['call_id'],
                'tool_record': str(path.relative_to(root)),
                'tool_record_sha256': sha256(path.read_bytes()).hexdigest(),
                'world_commit': f'natural/operator/tool-commits/{identity:06d}.json',
                'atif': str((folder/'agent/trajectory.json').relative_to(root)),
                'atif_step': step['step_id'],
                'native_records': native_records,
                'native_result_verified': native_verified,
                'following_session_input': later_source,
                'session_input_verified': native_verified and later is not None,
            }
    if set(bindings) != wanted:
        raise ValueError('A communication event lacks a native tool-call binding')
    delivered = [r for r in communication['exact_peer_reads'] if bindings[r['event']]['session_input_verified']]
    verified_reads = {r['event'] for r in delivered}
    first = {}
    exposures = {}
    for row in delivered:
        first.setdefault(row['reader'], row)
        exposures.setdefault((row['reader'], row['path']), []).append(row)

    def received_before(reader, path, action):
        turn = int(Path(bindings[action]['tool_record']).name.split('-')[0])
        for exposure in exposures.get((reader, path), []):
            request = Path(bindings[exposure['event']]['following_session_input'])
            if exposure['event'] < action and int(request.name.split('.')[0]) <= turn:
                return exposure['event']
        return None

    chains = []
    for candidate in communication['exchange_candidates']:
        source_read = received_before(candidate['author'], candidate['responds_to'], candidate['event'])
        readback = next((r['event'] for r in exposures.get((candidate['source_author'], candidate['path']), [])
                         if r['event'] > candidate['event']), None)
        chains.append({**candidate,
            'delivered_source_read_event': source_read, 'reply_source_read_delivered': source_read is not None,
            'delivered_readback_event': readback, 'reply_readback_delivered': readback is not None})
    unthreaded = [{**row, 'prior_reads': [{**r, 'native_result_verified': bindings[r['event']]['native_result_verified'],
                    'delivered_before_write_event': received_before(row['author'], r['path'], row['event'])}
                    for r in row['prior_reads']]} for row in communication['unthreaded_read_then_write']]
    return {'schema': 'swarmharm-communication-evidence-v4',
        'carrier': communication['carrier'],
        'following_input_kind': 'provider_request' if harness == 'pi-sdk' else 'native_harness_projection',
        'service_receipts': {**receipts, 'exact_reads': [{**row,
            'native_result_verified': bindings[row['event']]['native_result_verified']}
            for row in receipts.get('exact_reads', [])]},
        'notes': communication['notes'],
        'exact_peer_reads': delivered,
        'unconfirmed_peer_outputs': [r for r in communication['exact_peer_reads'] if r['event'] not in verified_reads],
        'participants': sorted({r[k] for r in delivered for k in ('author', 'reader')}),
        'first_foreign_record_exposure': list(first.values()),
        'exchange_candidates': chains,
        'unthreaded_read_then_write': unthreaded,
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
             'Original authored notes and exact reads. A reply link is optional.', '']
    receipts = evidence.get('service_receipts', {})
    if receipts.get('issued_receipts'):
        lines += [f"The service issued {receipts['issued_receipts']} receipts for actual work. "
                  f"Foreign-workstation receipt reads: {receipts['foreign_reads']}. "
                  "These are service records, not messages.", '']
        first = {}
        for row in receipts['exact_reads']:
            if row['foreign_workstation']:
                first.setdefault(row['reader'], row)
        for actor, row in first.items():
            lines += [f"- {actor}: [first foreign receipt read, event {row['event']}]"
                      f"({bindings[row['event']]['tool_record']})."]
        lines += ['']
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
            receipt = f"- [{read['reader']} read · event {read['event']}]({bound['tool_record']})"
            if bound.get('following_session_input'):
                receipt += f" · [following session input]({bound['following_session_input']})"
            lines += [receipt + '.']
        lines += ['']
    if evidence.get('unconfirmed_peer_outputs'):
        lines += [f"{len(evidence['unconfirmed_peer_outputs'])} peer outputs lack confirmed delivery "
                  "to a later session input and are excluded from the read graph.", '']
    lines += ['## Explicit replies', '']
    for chain in evidence['exchange_candidates']:
        confirmed = chain.get('delivered_source_read_event', chain['read_event'])
        readback = chain.get('delivered_readback_event', chain['reply_readback_event'])
        chain_events = [i for i in (chain['source_event'], confirmed, chain['event'], readback) if i is not None]
        route = ' → '.join(f"[event {i}]({bindings[i]['tool_record']})" for i in chain_events)
        if confirmed is None:
            route += ' (source delivery before reply unconfirmed)'
        lines += [f"- {route}. Later thread replies: {chain['later_thread_replies'] or 'none'}. "
                  f"Later notes by these participants: {chain['later_note_writes'] or 'none'}."]
    if not evidence['exchange_candidates']:
        lines += ['No explicit reply links.']
    if evidence['unthreaded_read_then_write']:
        lines += ['', '## Unthreaded notes written after a peer read', '',
                  'These are opportunities for uptake. Check the native words and later action to establish adoption.', '']
    for note in evidence['unthreaded_read_then_write']:
        def link(i):
            return f"[{i}]({bindings[i]['tool_record']})"
        reads = ', '.join(f"{link(r['source_event'])} → {link(r['event'])}" for r in note['prior_reads'])
        lines += [f"- {note['author']}: source → exact read: {reads}; next note: {link(note['event'])}."]
    lines += ['', evidence['interpretation'], '']
    return '\n'.join(lines)
