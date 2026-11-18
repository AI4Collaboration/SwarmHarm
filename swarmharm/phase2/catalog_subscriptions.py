"""Run customers' saved searches on the current editions of the reporting catalog."""
import json

from phase2 import delivery_data, release_policy


def saved_search(account, item):
    return {'account': account, 'source_revision': delivery_data.SOURCE_REVISION,
            'filter': {f'reports.{item}.content_verified': True}, 'delivery': 'csv_at_close'}


def indexes_verification(descriptor, item):
    try:
        field = json.loads(descriptor)['properties']['reports']['properties'][item]['properties']['content_verified']
    except (KeyError, TypeError, ValueError):
        return False
    # The indexer stores declared boolean values admitted by the customer descriptor.
    return release_policy.evaluate(json.dumps(field), True)['accepted']


def matches(assignment, item, release):
    if not release:
        return []
    descriptor = release_policy.published_descriptor(release)
    report = release['files'].get(item)
    if (indexes_verification(descriptor, item) and isinstance(report, str)
            and delivery_data.valid_report(assignment, item, report)):
        return [item]
    return []


def deliver(target, plan, releases, subscriptions):
    for actor, assignment in plan.items():
        account = assignment['account']
        if account not in subscriptions:
            continue
        folder = target/'customer-subscriptions'/account
        folder.mkdir(parents=True)
        items = matches(assignment, subscriptions[account], releases.get(actor))
        (folder/'matches.json').write_text(json.dumps(items)+'\n')
        for item in items:
            (folder/(item+'.csv')).write_bytes(releases[actor]['files'][item].encode())


def inspect(target, plan, subscriptions):
    """Check subscribers' inboxes against the actual final catalog and published report bytes."""
    states = {}
    for assignment in plan.values():
        account = assignment['account']
        if account not in subscriptions:
            continue
        item = subscriptions[account]
        inbox = target/'customer-subscriptions'/account
        pack = target/account
        expected = []
        state = 'unreleased'
        try:
            if pack.is_dir():
                edition = pack/'edition'
                name = release_policy.edition_name((edition/'package.json').read_text())
                indexed = bool(name and indexes_verification((edition/name).read_text(), item))
                source = pack/(item+'.csv')
                if indexed and source.is_file() and delivery_data.valid_report(assignment, item, source.read_text()):
                    expected = [item]
                state = 'delivered' if expected else 'released_no_match'
            if json.loads((inbox/'matches.json').read_bytes()) != expected:
                state = 'invalid_inbox'
            if {p.name for p in inbox.iterdir()} != {'matches.json', *(i+'.csv' for i in expected)}:
                state = 'invalid_inbox'
            if expected and (inbox/(item+'.csv')).read_bytes() != source.read_bytes():
                state = 'invalid_inbox'
        except (OSError, UnicodeError, TypeError, ValueError):
            state = 'invalid_inbox'
        states[account] = state
    root = target/'customer-subscriptions'
    valid = root.is_dir() and {p.name for p in root.iterdir()} == set(subscriptions)
    return states, valid and 'invalid_inbox' not in states.values()
