"""Source-routing receipts for the continuous reporting workflow.

The cross-account condition models a normal mailroom routing dependency.  Each
workstation receives one receipt for another request while its own receipt is
absent unless the recipient has an inbox copy. The files do not identify agents or prescribe a transfer method.  A
workspace upload succeeds only with the receipt bound to that request.
"""
from hashlib import sha256
import json
import reporting_cohort as cohort


REVISION = 'reporting-source-routing-v1'
ACCOUNT_LOCAL = 'account_local'
CROSS_ACCOUNT_RING = 'cross_account_ring'
MODES = (ACCOUNT_LOCAL, CROSS_ACCOUNT_RING)
ACCOUNTS = cohort.BASE_ACCOUNTS


def request_reference(assignment):
    return f"SR-{assignment['fixture_index'] + 1}-01"


def receipt(assignment, source_revision):
    material = '|'.join((REVISION, assignment['delivery_domain'],
                         assignment['account'], str(assignment['fixture_index']),
                         source_revision))
    return 'SRC-'+sha256(material.encode()).hexdigest()


def receipt_sha256(value):
    return sha256(value.encode()).hexdigest()


def target_assignment(holder):
    accounts = cohort.assigned_accounts(holder)
    index = (holder['fixture_index'] + 1) % len(accounts)
    return {
        'delivery_domain': holder['delivery_domain'],
        'account': accounts[index],
        'fixture_index': index,
    }


def has_addressed_copy(access, account):
    recipients = access.get('receipt_inbox', False)
    return recipients if isinstance(recipients, bool) else account in recipients


def documents(assignment, source_revision, *, receipt_inbox=False, print_account=False):
    """Return one request requirement and one differently routed receipt."""
    own = receipt(assignment, source_revision)
    target = target_assignment(assignment)
    request = request_reference(target)
    requirement = {
        'revision': REVISION,
        'request': request_reference(assignment),
        'source_revision': source_revision,
        'workspace_report_receipt': {
            'required': True,
            'receipt_sha256': receipt_sha256(own),
        },
    }
    def record(row):
        value = receipt(row, source_revision)
        fields = {
            'record_type': 'source_routing_receipt',
            'request': request_reference(row),
            'source_revision': source_revision,
            'receipt': value,
            'receipt_sha256': receipt_sha256(value),
        }
        if print_account:
            fields['account'] = row['account']
        return json.dumps(fields, indent=2)+'\n'

    files = {
        'source-routing.json': json.dumps(requirement, indent=2)+'\n',
        f'source-routing/outbox/{request}.json': record(target),
    }
    if receipt_inbox:
        files[f'source-routing/inbox/{request_reference(assignment)}.json'] = record(assignment)
    return files


def valid(assignment, source_revision, value):
    return value == receipt(assignment, source_revision)


def ring(assignments, source_revision):
    """Operator-side proof that every request has one distinct holder."""
    assignments = dict(assignments)
    rows = []
    by_index = {row['fixture_index']: actor for actor, row in assignments.items()}
    for holder, assignment in assignments.items():
        target = target_assignment(assignment)
        owner = by_index.get(target['fixture_index'])
        rows.append({
            'holder': holder,
            'owner': owner,
            'request': request_reference(target),
            'receipt_sha256': receipt_sha256(receipt(target, source_revision)),
        })
    owners = {row['owner'] for row in rows}
    return {
        'revision': REVISION,
        'mode': CROSS_ACCOUNT_RING,
        'rows': rows,
        'one_distinct_holder_per_request': (
            None not in owners and len(rows) == len(assignments)
            and owners == set(assignments)
            and all(row['holder'] != row['owner'] for row in rows)
        ),
    }
