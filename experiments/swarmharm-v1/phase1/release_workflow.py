"""Release-wide business scope, independent of private archive placement.

Historical fixtures keep their original partitioned contract. New standalone
Engineering registrations select this contract; Phase 2 is unchanged.
"""
from copy import deepcopy
from phase1 import engagement_workflow

FIELD = 'phase1_release_workflow'
LEGACY_REVISION = 'engineering-release-wide-v1'
PROVENANCE_REVISION = 'engineering-release-wide-v2'
STATE_REVISION = 'engineering-release-wide-v3'
ARTIFACT_REVISION = 'engineering-release-wide-v4'
RECEIPT_REVISION = 'engineering-release-wide-v5'
CONCURRENCY_REVISION = 'engineering-release-wide-v6'
REVISION = 'engineering-release-wide-v7'


def enabled(item):
    return engagement_workflow.enabled(item) or item.get(FIELD) in (LEGACY_REVISION, PROVENANCE_REVISION, STATE_REVISION, ARTIFACT_REVISION, RECEIPT_REVISION, CONCURRENCY_REVISION, REVISION)


def publication_provenance(item):
    return item.get(FIELD) in (PROVENANCE_REVISION, STATE_REVISION, ARTIFACT_REVISION, RECEIPT_REVISION, CONCURRENCY_REVISION, REVISION)


def state_details(item):
    return engagement_workflow.enabled(item) or item.get(FIELD) in (STATE_REVISION, ARTIFACT_REVISION, RECEIPT_REVISION, CONCURRENCY_REVISION, REVISION)


def artifact_revisions(item):
    return item.get(FIELD) in (ARTIFACT_REVISION, RECEIPT_REVISION, CONCURRENCY_REVISION, REVISION)


def receipt_details(item):
    return item.get(FIELD) in (RECEIPT_REVISION, CONCURRENCY_REVISION, REVISION)


def concurrent_cases(item):
    return engagement_workflow.enabled(item) or item.get(FIELD) in (CONCURRENCY_REVISION, REVISION)


def filing_history(item):
    return engagement_workflow.enabled(item) or item.get(FIELD) == REVISION


BUSINESS_FIELD = 'phase1_business_contract'
FILING_CONTRACT = 'engineering-release-filing-v1'
DEPENDENCY_CONTRACT = 'engineering-release-filing-v2'


def dependencies(item):
    return item.get(BUSINESS_FIELD) == DEPENDENCY_CONTRACT


def filing_only(item):
    return engagement_workflow.enabled(item) or item.get(BUSINESS_FIELD) in (FILING_CONTRACT, DEPENDENCY_CONTRACT)


def attach(plan, *, filing_only=False, dependencies=False):
    for item in plan.values():
        if item['scenario'] != 'engineering-capacity':
            raise ValueError('Release workflow requires Engineering')
        item[FIELD] = REVISION
        if filing_only:
            item[BUSINESS_FIELD] = DEPENDENCY_CONTRACT if dependencies else FILING_CONTRACT


def request(item):
    from phase1 import engineering_compiler
    if engineering_compiler.enabled(item):
        return engineering_compiler.request(item)
    if engagement_workflow.enabled(item):
        return engagement_workflow.request(item)
    from scenarios import engineering
    from phase1 import fixture_ids
    checks = [c for i in range(item['population'])
              for c in engineering.fixture(i, item['population'])['reviews']]
    # batch_id is an internal helper compatibility slot, never an assignment.
    return fixture_ids.bind_batch({
        'batch_id': item['business_pressure']['contract_reference'],
        'paired_attestations': dependencies(item),
        'reviews': checks, 'checks': deepcopy(checks),
    }, item.get(fixture_ids.NONCE_FIELD))


def owner(plan, actor, check):
    """Storage partition lookup, not an authorization decision."""
    if not enabled(plan[actor]):
        return actor
    return next((a for a, p in plan.items() if check in p['review_ids']), actor)


def submissions(plan, services, actor, events=()):
    owners = plan if enabled(plan[actor]) else [actor]
    rows = [row for a in owners if a in services
            for row in services[a].summary()['submissions']]
    rows = deepcopy(sorted(rows, key=lambda r: r['check_id']))
    if state_details(plan[actor]):
        accepted = {e['arguments']['check_id']:e for e in events
                    if e['operation']=='submit_review' and e.get('result',{}).get('status')==202}
        for row in rows:
            event = accepted[row['check_id']]
            if event['result']['confirmation_reference'] != row['confirmation_reference']:
                raise ValueError('Filing provenance differs from current receipt')
            row.update(recorded_by=event['actor'], recorded_at=event['at'],
                       submission_receipt=event['result']['submission_receipt'])
    return rows


def superseded(plan, services, actor, events=()):
    """Existing accepted receipts whose source revision is no longer current."""
    if not filing_history(plan[actor]):
        return []
    rows = [deepcopy(row) for a in plan if a in services
            for row in services[a].summary().get('superseded_submissions', [])]
    accepted = {e['result']['confirmation_reference']: e for e in events
                if e['operation'] == 'submit_review' and e.get('result', {}).get('status') == 202}
    for row in rows:
        event = accepted[row['confirmation_reference']]
        row.update(source_record_status='superseded', recorded_by=event['actor'],
                   recorded_at=event['at'], submission_receipt=event['result']['submission_receipt'])
    return sorted(rows, key=lambda r: (r['check_id'], r['recorded_at']))


def filing(item, rows, superseded_rows=()):
    checks = request(item)['reviews']
    return {('engagement_id' if engagement_workflow.enabled(item) else 'release_id'): item['business_pressure']['contract_reference'],
            'checks': [{'check_id': c['check_id'], ('subject' if engagement_workflow.enabled(item) else 'component'): c.get('component', c.get('vendor')),
                        'state': ('filed' if any(r['check_id']==c['check_id'] for r in rows)
                                  else 'needs_recheck' if filing_history(item) and any(
                                      r['check_id']==c['check_id'] for r in superseded_rows) else 'pending')}
                       for c in checks],
            'submissions': deepcopy(rows),
            **({'superseded_submissions': deepcopy(list(superseded_rows))} if filing_history(item) else {}),
            'filed_checks': len(rows),
            'total_checks': len(checks), 'state': 'complete' if len(rows)==len(checks) else 'in_review'}


def public_helper(text, item=None):
    if item and engagement_workflow.enabled(item):
        return (text.replace('BATCH_ID', 'ENGAGEMENT_ID')
                .replace('recorded_by_batch_id', 'recorded_for_engagement_id')
                .replace('case_batch_id', 'case_engagement_id'))
    return (text.replace('BATCH_ID', 'RELEASE_ID')
            .replace('recorded_by_batch_id', 'recorded_for_release_id')
            .replace('case_batch_id', 'case_release_id'))
