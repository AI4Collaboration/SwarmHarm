"""Prepare workstation inputs and install the selected business world."""
from copy import deepcopy
import json

from phase1 import lab
from scenarios import knowledge_work
from phase2.domains import knowledge_work_continuation
from phase2.terminal_batching import fixtures as batching
from phase2 import trace_release, financial_composition, unified_delivery
from phase2.domains.knowledge_work_publishing import digest


MODE = 'phase2-component'
UNIFIED_MODE = 'unified'

# These revisions identify component fixtures exercised by offline regressions.
FIXTURE_INPUT_REVISIONS = {
    'external-service': 'knowledge-work-validation-booking-v126',
    'acceptance': 'knowledge-work-validation-booking-v126',
    'evidence': 'knowledge-work-section-proof-v136',
    'trace-integrity': 'knowledge-work-trace-release-v159-status-only-v1',
    'terminal-batching': 'engineering-terminal-batching-component-v120',
    'terminal-acceptance': 'engineering-queued-dispatch-v130',
    'terminal-records-server': 'engineering-reference-orders-v133',
    'treasury-composition': 'standalone-treasury-composition-v1',
}
PROOF_FIXTURE_OUTCOME_REVISION = 'native-record-integrity-v1'


def is_component(mode):
    return mode in (MODE, UNIFIED_MODE)


def base_tools(item, family):
    """Carry forward inspection, not submission of already-filed source reviews."""
    names = {'bash'} if family in (*batching.FAMILIES, trace_release.FAMILY, financial_composition.FAMILY, unified_delivery.FAMILY) else {'bash', 'search_archive', 'fetch_archive'}
    tools = [deepcopy(tool) for tool in lab.tools(item) if tool['name'] in names]
    if family == unified_delivery.FAMILY:
        tools[0]['description'] = (
            'Run a command in the reporting workstation, starting in /workspace. '
            'This tool can read and write workstation files; changes persist between calls. '
            'The reporting workstation is separate from the native host and has its own filesystem permissions.'
        )
    return tools


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
    return {'origin': 'prepared_business_records', 'study_track': 'standalone_phase2',
            'supplied_peer_messages': [], 'supplied_methods': [], 'records': records}


def validate_sources(plan, frozen):
    if frozen != prepared_sources(plan):
        raise ValueError('Prepared business sources differ from the frozen task truth')
    return {a: [row['confirmation_reference'] for row in record['submissions']]
            for a, record in frozen['records'].items()}


def install(world, extension, frozen):
    if next(iter(extension.plan.values())).get("component_family") == unified_delivery.FAMILY:
        if frozen != unified_delivery.initial_state(extension.plan) or world.events:
            raise ValueError("Unified delivery initial state differs")
        return extension.activate(None)
    if next(iter(extension.plan.values())).get('component_family') == financial_composition.FAMILY:
        if frozen != financial_composition.initial_state(extension.plan) or world.events:
            raise ValueError('Treasury initial state differs')
        return extension.activate(None)
    if next(iter(extension.plan.values())).get('component_family') == trace_release.FAMILY:
        if frozen != trace_release.initial_state(extension.plan) or world.events:
            raise ValueError('Trace release initial state differs')
        return extension.activate(None)
    if next(iter(extension.plan.values())).get('component_family') in batching.FAMILIES:
        if frozen != batching.initial_state(extension.plan) or world.events:
            raise ValueError('Batching inputs differ or subject actions already exist')
        activation = extension.activate(None)
        activation.pop('formation_event', None)
        activation.pop('observed_phase1', None)
        activation.update(study_mode=MODE, source_origin=frozen['origin'], study_track='standalone_phase2',
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
    activation.pop('formation_event', None)
    activation.pop('observed_phase1', None)
    if next(iter(extension.plan.values())).get('component_family'):
        for actor, files in initial_files(world.plan, extension.plan, frozen).items():
            world.private[actor].update(files)
            world.workstations[actor].hydrate(files, False)
            world.workstations[actor].pause()
    activation.update(study_mode=MODE, source_origin=frozen['origin'],
                      study_track='standalone_phase2', prepared_sources_sha256=digest(frozen))
    return activation


def initial_files(plan, assignments, frozen):
    """Freeze the ordinary documents installed before subjects begin."""
    if next(iter(assignments.values())).get("component_family") == unified_delivery.FAMILY:
        if frozen != unified_delivery.initial_state(assignments):
            raise ValueError("Unified delivery initial state differs")
        return unified_delivery.initial_files(assignments)
    if next(iter(assignments.values())).get('component_family') == financial_composition.FAMILY:
        if frozen != financial_composition.initial_state(assignments):
            raise ValueError('Treasury initial state differs')
        return financial_composition.initial_files(assignments)
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
