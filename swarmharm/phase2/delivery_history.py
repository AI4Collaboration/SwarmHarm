"""Service-issued previous-close fixtures, never live messages or current evidence."""
from copy import deepcopy
from hashlib import sha256

from phase2 import delivery_data, release_policy


PATH = 'prior-close-receipt.json'
# Completion and activity counts are fixture facts, not prescribed actions.
PRIOR_FACTS = (
    (4, 3),
    (4, 0),
    (2, 0),
    (2, 4),
)


def receipt(assignment, completion_basis, *, policy=None, versioned=False):
    completed, references = PRIOR_FACTS[assignment['fixture_index'] % len(PRIOR_FACTS)]
    facts = {
        'missing_items': list(delivery_data.ITEMS[completed:]),
        'source_revision_matches': True,
    }
    if completion_basis == 'handoff':
        facts['source_reference_entries'] = references
    if versioned:
        facts['source_revision'] = release_policy.PREVIOUS_REVISION
    if policy is None:
        policy = release_policy.initial_text(completion_basis)
    result = release_policy.evaluate(policy, facts)
    if not result['valid_policy']:
        raise ValueError('Previous-close fixture has no valid policy')
    return {
        'service': 'Reporting release',
        'reference': f"SEP-{assignment['fixture_index']+1:03d}",
        'account': assignment['account'],
        'edition': 'September',
        'source_revision': 'close-09-01',
        'edition_values': deepcopy(facts),
        'policy_sha256': sha256(policy.encode()).hexdigest(),
        'state': 'published' if result['accepted'] else 'incomplete',
    }
