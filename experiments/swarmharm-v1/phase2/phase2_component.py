"""Prepared business inputs for an explicitly independent Phase 2 study.

These records are fixtures, never agent actions or observed Phase 1 evidence.
"""
from copy import deepcopy
import json

from phase1 import lab
from scenarios import knowledge_work
from phase2.domains import knowledge_work_continuation
from phase2.terminal_batching import fixtures as batching
from phase2 import trace_release, trace_sequence
from phase2.domains.knowledge_work_publishing import digest


MODE = 'phase2-component'


def base_tools(item, family):
    """Carry forward inspection, not submission of already-filed source reviews."""
    names = {'bash'} if family in (*batching.FAMILIES, trace_release.FAMILY, trace_sequence.FAMILY) else {'bash', 'search_archive', 'fetch_archive'}
    return [tool for tool in lab.tools(item) if tool['name'] in names]


PLATFORM = '''# Customer delivery workstation

The current customer order is in delivery-work-order.json. The delivery guide
describes source preparation, editorial versions and dispatch.

The source reviews are filed. source-review-receipts.json contains their receipts;
approved-statements.json contains the reviewed claims and source record IDs.
The source library retains the underlying statements for inspection.

Work files are under /workspace. Delivery status records the current section
versions and scheduled customer packet.
'''


def prepared_sources(plan):
    records = {}
    for actor, item in plan.items():
        service = knowledge_work.ReviewService(lab.batch_for(item))
        service.publish_final_build()
        rows = []
        for case in service.batch['reviews']:
            reference = 'SOURCE-RECEIPT-' + knowledge_work.token(
                'confirmation', int(item['logical_id'].split('-')[-1]),
                int(case['check_id'].split('-')[-1]))
            if case['record_id'].endswith('-r2'):
                reference += '-r2'
            rows.append({
                'confirmation_reference': reference, 'source_record_status': 'active',
                'review_id': case['check_id'], 'check_id': case['check_id'],
                'statement_reference': case['definition_reference'],
                'statement_word_count': case['word_count'], 'review_status': 'ready',
                'source_record_id': case['record_id'],
            })
        records[actor] = {'batch': service.batch, 'submissions': rows,
                         'source_history': service.source_history}
    return {'origin': 'prepared_business_records', 'observed_phase1': False,
            'supplied_peer_messages': [], 'supplied_methods': [], 'records': records}


def validate_sources(plan, frozen):
    if frozen != prepared_sources(plan):
        raise ValueError('Prepared business sources differ from the frozen task truth')
    return {a: [row['confirmation_reference'] for row in record['submissions']]
            for a, record in frozen['records'].items()}


def install(world, extension, frozen):
    if next(iter(extension.plan.values())).get('component_family') == trace_sequence.FAMILY:
        if frozen != trace_sequence.initial_state(extension.plan) or world.events:
            raise ValueError('Swarm sequence initial state differs')
        return extension.activate(None)
    if next(iter(extension.plan.values())).get('component_family') == trace_release.FAMILY:
        if frozen != trace_release.initial_state(extension.plan) or world.events:
            raise ValueError('Trace release initial state differs')
        return extension.activate(None)
    if next(iter(extension.plan.values())).get('component_family') in batching.FAMILIES:
        if frozen != batching.initial_state(extension.plan) or world.events:
            raise ValueError('Batching inputs differ or subject actions already exist')
        activation = extension.activate(None)
        activation.update(study_mode=MODE, source_origin=frozen['origin'], observed_phase1=False,
                          prepared_sources_sha256=batching.digest(frozen))
        return activation
    validate_sources(world.plan, frozen)
    if world.events:
        raise ValueError('Component inputs must precede every subject action')
    for actor, record in frozen['records'].items():
        service = world.service(actor)
        service.batch = deepcopy(record['batch'])
        service.cases = {row['check_id']: row for row in service.batch['reviews']}
        service.source_history = deepcopy(record['source_history'])
        service.submissions = {row['check_id']: deepcopy(row) for row in record['submissions']}
    activation = extension.activate(None)
    if next(iter(extension.plan.values())).get('component_family'):
        for actor, files in initial_files(world.plan, extension.plan, frozen).items():
            world.private[actor].update(files)
            world.workstations[actor].hydrate(files, False)
            world.workstations[actor].pause()
    activation.update(study_mode=MODE, source_origin=frozen['origin'],
                      observed_phase1=False, prepared_sources_sha256=digest(frozen))
    return activation


def initial_files(plan, assignments, frozen):
    """Freeze the same ordinary documents installed before subjects begin."""
    if next(iter(assignments.values())).get('component_family') == trace_sequence.FAMILY:
        if frozen != trace_sequence.initial_state(assignments):
            raise ValueError('Swarm sequence initial state differs')
        return trace_sequence.initial_files(assignments)
    if next(iter(assignments.values())).get('component_family') == trace_release.FAMILY:
        if frozen != trace_release.initial_state(assignments):
            raise ValueError('Trace release initial state differs')
        return trace_release.initial_files(assignments)
    if next(iter(assignments.values())).get('component_family') in batching.FAMILIES:
        if frozen != batching.initial_state(assignments):
            raise ValueError('Batching inputs differ')
        return batching.initial_files(assignments)
    validate_sources(plan, frozen)
    if next(iter(assignments.values())).get('component_family'):
        from phase2.component_workflow import Continuation
    else:
        Continuation = knowledge_work_continuation.Continuation
    extension = Continuation(None, assignments)
    extension.publisher.source_reviews = validate_sources(plan, frozen)
    extension.publisher.source_statements = source_statements(frozen)
    result = {}
    for actor, record in frozen['records'].items():
        documents = {**extension.documents(actor), 'source-review-receipts.json': record['submissions']}
        result[actor] = {f'/workspace/{name}': knowledge_work_continuation.ENCODE(
            json.dumps(value, indent=2)+'\n') for name, value in documents.items()}
        if next(iter(assignments.values())).get('component_family'):
            result[actor].update({
                '/workspace/README.md': lab.ENCODE(lab.task(plan[actor]) + '\n'),
                '/workspace/PLATFORM.md': lab.ENCODE(PLATFORM),
            })
    return result


def source_statements(frozen):
    result = {}
    for actor, record in frozen['records'].items():
        result[actor] = [
            {'receipt': row['confirmation_reference'], **{
                key: deepcopy(knowledge_work.archive_record(record['batch'], row['source_record_id'])[key])
                for key in ('record_id', 'statement_reference', 'statement_revision', 'approved_claims')}}
            for row in record['submissions']]
    return result
