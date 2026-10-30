"""Prepared business inputs for an explicitly independent Phase 2 study.

These records are fixtures, never agent actions or observed Phase 1 evidence.
"""
from copy import deepcopy
import json

import lab
from domains import knowledge_work
from domains import knowledge_work_continuation
from domains.knowledge_work_publishing import digest


MODE = 'phase2-component'


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
    activation.update(study_mode=MODE, source_origin=frozen['origin'],
                      observed_phase1=False, prepared_sources_sha256=digest(frozen))
    return activation


def initial_files(plan, assignments, frozen):
    """Freeze the same ordinary documents installed before subjects begin."""
    validate_sources(plan, frozen)
    extension = knowledge_work_continuation.Continuation(None, assignments)
    extension.publisher.source_reviews = validate_sources(plan, frozen)
    extension.publisher.source_statements = source_statements(frozen)
    result = {}
    for actor, record in frozen['records'].items():
        documents = {**extension.documents(actor), 'source-review-receipts.json': record['submissions']}
        result[actor] = {f'/workspace/{name}': knowledge_work_continuation.ENCODE(
            json.dumps(value, indent=2)+'\n') for name, value in documents.items()}
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
