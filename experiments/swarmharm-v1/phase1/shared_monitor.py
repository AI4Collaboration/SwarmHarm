"""Observe the exposed shared workspace, without supplying a communication method."""
from copy import deepcopy
from hashlib import sha256
import json

from phase1 import shared_files, engineering_planning

REVISION = 'shared-environment-monitor-v1'


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inventory(plan):
    if shared_files.descriptor(plan) is None:
        return None
    knowledge = next(iter(plan.values()))['scenario'] == 'knowledge-work'
    return {'revision': REVISION, 'subject_visible': False,
            'surfaces': [
                {'id': 'project_files', 'roots': list(shared_files.ROOTS),
                 'recorded': ['accepted_changes', 'returned_names', 'returned_contents']},
                {'id': 'investigation_records', 'roots': ['/registry/cache/reviews'],
                 'recorded': ['authored_records', 'exact_reads', 'linked_updates', 'source_attachments']},
                {'id': 'filing_state', 'operations': (['submit_release_plan', 'release_plan_status']
                    if engineering_planning.descriptor(plan) else ['submit_review', 'filing_status']),
                 'recorded': ['accepted_receipts', 'rejections', 'current_and_superseded_rows']},
                *([{'id': 'briefing_delivery', 'operations': ['publish_briefing', 'filing_status'],
                    'recorded': ['published_bytes', 'returned_publication']}] if knowledge else []),
                {'id': 'platform_notices',
                 'recorded': ['source_records', 'before_and_after_signals', 'exact_native_input']}],
            'boundary': 'Private workstations have no cross-workstation network or shared OS namespace. '
                        'Registry synchronization occurs at tool boundaries.',
            'inference': 'Exposure is distinct from intentional communication and formation.'}


def filing_replay(plan, events):
    """Rebuild service state before attributing returned rows to accepted actions."""
    if engineering_planning.descriptor(plan):
        return engineering_planning.replay(plan, events)
    if inventory(plan) is None:
        return {'samples': [], 'foreign_observations': []}
    import domain_runtime
    from phase1 import lab, release_workflow, engagement_workflow
    scenario = domain_runtime.mechanics(next(iter(plan.values()))['scenario'])
    services = {actor: scenario.ReviewService(lab.batch_for(item)) for actor, item in plan.items()}
    reads = {actor: set() for actor in plan}
    accepted, prefix, samples, observations = {}, [], [], []
    publication = None
    publication_event = None

    def require(test, message):
        if not test:
            raise ValueError(message)

    def observe(source, event, feature, returned):
        if source['actor'] != event['actor']:
            observations.append({'carrier': 'data_object', 'surface': 'filing_state',
                'feature': feature, 'source_event': source['id'], 'read_event': event['id'],
                'author': source['actor'], 'reader': event['actor'], 'sha256': digest(returned)})

    for event in events:
        actor, op, args, result = (event[k] for k in ('actor', 'operation', 'arguments', 'result'))
        sources = []
        if op == 'publish_final_build':
            expected = {a: service.publish_final_build() for a, service in services.items()}
            require(result == {'status': 200, 'revised_checks': expected}, 'Shared source update differs')
        elif actor not in plan:
            pass
        elif op == 'fetch_archive' and result.get('status') == 200:
            reads[actor].add(args['record_id'])
        elif op == 'submit_review' and result.get('status') != 400:
            owner = release_workflow.owner(plan, actor, args.get('check_id'))
            expected = services[owner].submit(args, reads[actor])
            require(expected['status'] == result['status'], 'Shared filing acceptance differs')
            if expected['status'] == 202:
                receipt = expected['_receipt']
                require(receipt['confirmation_reference'] == result['confirmation_reference'],
                        'Shared filing receipt differs')
                accepted[result['confirmation_reference']] = event
                sources = [event['id']]
            elif result['status'] == 409 and args.get('check_id') in services[owner].submissions:
                row = services[owner].submissions[args['check_id']]
                source = accepted[row['confirmation_reference']]
                # Missing local receipts can also return 409. It is not a foreign-status observation.
                if 'already filed' in result.get('error', '').lower():
                    sources = [source['id']]
                    observe(source, event, 'filing_already_filed', result)
        elif op == 'publish_briefing' and result.get('status') != 400:
            expected = engagement_workflow.publish_briefing(plan, services, actor, reads[actor], args)
            require(expected == result, 'Shared briefing publication differs')
            if result['status'] == 201:
                publication, publication_event = deepcopy(result['publication']), event
                sources = [event['id']]
        elif op == 'filing_status' and result.get('status') == 200:
            filing = release_workflow.filing(plan[actor],
                release_workflow.submissions(plan, services, actor, prefix),
                release_workflow.superseded(plan, services, actor, prefix))
            expected = {'status': 200, 'filing': filing}
            if plan[actor]['scenario'] == 'knowledge-work':
                expected.update(briefing=publication,
                    briefing_current=engagement_workflow.briefing_current(plan, services, publication))
            require(expected == result, 'Shared filing status differs from accepted sources')
            for group in ('submissions', 'superseded_submissions'):
                for row in filing.get(group, []):
                    source = accepted[row['confirmation_reference']]
                    sources.append(source['id'])
                    observe(source, event, 'filing_receipt', row)
            if publication_event is not None:
                sources.append(publication_event['id'])
                observe(publication_event, event, 'briefing_publication', publication)
        if op in ('submit_review', 'filing_status', 'publish_briefing'):
            samples.append({'event': event['id'], 'actor': actor, 'operation': op,
                            'status': result.get('status'), 'result_sha256': digest(result),
                            'source_events': sorted(set(sources))})
        prefix.append(event)
    return {'samples': samples, 'foreign_observations': observations}


def notice_sources(world, signal, previous):
    """Capture operator-side causes. This object never becomes subject input."""
    changed = [case for case, revision in signal.get('case_revisions', {}).items()
               if previous.get('case_revisions', {}).get(case) != revision]
    current_entries = signal.get('monitored_case_entries', signal.get('case_entries', {}))
    previous_entries = previous.get('monitored_case_entries', previous.get('case_entries', {}))
    entries = [row for case in changed for row in current_entries.get(case, [])
               if (row['path'], row['sha256']) not in {
                   (r['path'], r['sha256']) for r in previous_entries.get(case, [])}]
    sources = []
    for row in entries:
        matches = [(event, record) for event in world.events for record in event.get('shared_changes', [])
                   if record.get('path') == row['path'] and record.get('sha256') == row['sha256']]
        if not matches:
            raise ValueError('Platform notice has no recorded source')
        event, record = matches[-1]
        sources.append({'event': event['id'], 'author': event['actor'],
                        'path': record['path'], 'sha256': record['sha256']})
    publication = signal.get('source_publication_event')
    if publication is not None and publication != previous.get('source_publication_event'):
        sources.append({'event': publication, 'author': None, 'kind': 'source_publication'})
    return {'revision': REVISION, 'before': deepcopy(previous), 'after': deepcopy(signal),
            'source_records': sources, 'world_event_count': len(world.events)}


def review(root, registration, world, mechanical):
    """Bind shared-state observations and notification inputs to native evidence."""
    from pathlib import Path
    from phase1 import carrier_trace_review as native
    plan = registration['plan']['natural']
    if inventory(plan) is None:
        return None
    root = Path(root).resolve()
    events = {event['id']: event for event in world['events']}
    filing = filing_replay(plan, world['events'])
    deliveries = []
    for event_id in sorted({row['read_event'] for row in mechanical['foreign_observations']}
                           | {row['event'] for row in filing['samples']}):
        event = events[event_id]
        binding = native.native_call(root, registration, event, sealed=True)
        delivered = None
        for path in sorted((root/'natural'/event['actor']/'trace').glob('*.request.json')):
            request, _ = native.read_file(root, path, True)
            if any(item.get('type') == 'function_call_output' and item.get('call_id') == binding['call_id']
                   for item in request['input']):
                delivered = native.delivered_in(root, registration, event, binding,
                    int(path.name.split('.')[0]), sealed=True)
                break
        deliveries.append({'event': event_id, 'native': binding, 'subsequent_input': delivered})
    notices = []
    for actor in plan:
        folder = root/'natural'/actor
        for path in sorted((folder/'trace').glob('*-platform-update.json')):
            notice, reference = native.read_file(root, path, True)
            source = notice.get('shared_monitor')
            if not source or source.get('revision') != REVISION:
                raise ValueError('Platform notice has no shared-surface monitoring record')
            from types import SimpleNamespace
            expected = notice_sources(SimpleNamespace(events=world['events'][:source['world_event_count']]),
                                      source['after'], source['before'])
            if source != expected:
                raise ValueError('Platform notice source binding differs')
            if source['after']['revision'] != notice['notice']['activity_revision']:
                raise ValueError('Platform notice revision differs from monitored state')
            echoes = []
            # Use the native user-message echo, rather than just the controller's intent to send.
            if registration['harness']['kind'] == 'codex':
                step = notice['notice']['step']
                request_path = folder/'trace'/f'{step:04d}.request.json'
                request = native.read_file(root, request_path, True)[0] if request_path.exists() else {}
                for relative in request.get('native_input_records', []):
                    entry = folder/'codex'/relative
                    record, ref = native.read_file(root, entry, True)
                    message = record['message']; item = (message.get('params') or {}).get('item') or {}
                    if (message.get('method') == 'rawResponseItem/completed' and item.get('role') == 'user'
                            and '\n'.join(p.get('text', '') for p in item.get('content', []))
                            == notice['input_message']['content']):
                        echoes.append(ref)
                # The input projection is cumulative. The last matching native
                # input is this notification; earlier copies are previous notices.
                echoes = echoes[-1:]
            notices.append({'actor': actor, 'record': reference, 'sources': source['source_records'],
                            'native_echoes': echoes, 'content': notice['input_message']['content'],
                            'intentional_communication_inferred': False})
    return {'revision': REVISION, 'inventory': inventory(plan),
            'filing_samples': filing['samples'], 'native_deliveries': deliveries,
            'notifications': notices, 'foreign_observations': mechanical['foreign_observations'],
            'intentional_communication_inferred': False}
