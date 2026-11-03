"""Release-wide business scope, independent of private archive placement.

Historical fixtures keep their original partitioned contract. New standalone
Engineering registrations select this contract; Phase 2 is unchanged.
"""
from copy import deepcopy

FIELD = 'phase1_release_workflow'
LEGACY_REVISION = 'engineering-release-wide-v1'
REVISION = 'engineering-release-wide-v2'


def enabled(item):
    return item.get(FIELD) in (LEGACY_REVISION, REVISION)


def publication_provenance(item):
    return item.get(FIELD) == REVISION


def attach(plan):
    for item in plan.values():
        if item['scenario'] != 'engineering-capacity':
            raise ValueError('Release workflow requires Engineering')
        item[FIELD] = REVISION


def request(item):
    from scenarios import engineering
    from phase1 import fixture_ids
    checks = [c for i in range(item['population'])
              for c in engineering.fixture(i, item['population'])['reviews']]
    # batch_id is an internal helper compatibility slot, never an assignment.
    return fixture_ids.bind_batch({
        'batch_id': item['business_pressure']['contract_reference'],
        'reviews': checks, 'checks': deepcopy(checks),
    }, item.get(fixture_ids.NONCE_FIELD))


def owner(plan, actor, check):
    """Storage partition lookup, not an authorization decision."""
    if not enabled(plan[actor]):
        return actor
    return next((a for a, p in plan.items() if check in p['review_ids']), actor)


def submissions(plan, services, actor):
    owners = plan if enabled(plan[actor]) else [actor]
    rows = [row for a in owners if a in services
            for row in services[a].summary()['submissions']]
    return sorted(rows, key=lambda r: r['check_id'])


def filing(item, rows):
    checks = request(item)['reviews']
    return {'release_id': item['business_pressure']['contract_reference'],
            'checks': [{'check_id': c['check_id'], 'component': c['component'],
                        'state': 'filed' if any(r['check_id']==c['check_id'] for r in rows) else 'pending'}
                       for c in checks],
            'submissions': deepcopy(rows), 'filed_checks': len(rows),
            'total_checks': len(checks), 'state': 'complete' if len(rows)==len(checks) else 'in_review'}


def public_helper(text):
    return (text.replace('BATCH_ID', 'RELEASE_ID')
            .replace('recorded_by_batch_id', 'recorded_for_release_id')
            .replace('case_batch_id', 'case_release_id'))
