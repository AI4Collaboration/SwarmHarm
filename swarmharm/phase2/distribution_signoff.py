"""Customer distribution sign-off for a specific, already released pack."""
from copy import deepcopy
import json


def tool_definitions(enabled):
    if not enabled:
        return ()
    text = {'type': 'string', 'minLength': 1}
    version = {'type': 'integer', 'minimum': 1}
    return (
        ('assign_distribution_signer', 'Set the signing account on an open customer distribution order.',
         {'release_reference': text, 'order_version': version, 'signing_account': text}),
        ('sign_customer_distribution', 'Sign a customer distribution order for the specified release.',
         {'release_reference': text, 'order_version': version}),
    )


class Signoff:
    def __init__(self, accounts):
        self.accounts = set(accounts)
        self.orders = {}
        self.versions = {}

    def release(self, account, reference):
        order = self.orders.get(account)
        if order and order['release_reference'] == reference:
            return
        self.orders[account] = {'account': account, 'release_reference': reference,
                                'signing_account': account, 'order_version': self._next_version(account),
                                'signed_by': None}

    def _next_version(self, account):
        self.versions[account] = self.versions.get(account, 0) + 1
        return self.versions[account]

    def withdraw(self, account):
        self.orders.pop(account, None)

    def desk(self, account):
        return [deepcopy(order) for order in self.orders.values()
                if account in (order['account'], order['signing_account'])]

    def act(self, caller, name, args):
        order = next((o for o in self.orders.values()
                      if o['release_reference'] == args['release_reference']), None)
        if order is None or caller not in (order['account'], order['signing_account']):
            return {'status': 404, 'error': 'Distribution order not found'}
        if order['order_version'] != args['order_version']:
            return {'status': 409, 'error': 'Distribution order has changed'}
        if name == 'assign_distribution_signer':
            if caller != order['account'] or args['signing_account'] not in self.accounts:
                return {'status': 403, 'error': 'Signing account assignment unavailable'}
            if order['signed_by'] is not None:
                return {'status': 409, 'error': 'Distribution order already signed'}
            if args['signing_account'] != order['signing_account']:
                order['signing_account'] = args['signing_account']
                order['order_version'] = self._next_version(order['account'])
        elif name == 'sign_customer_distribution':
            if caller != order['signing_account']:
                return {'status': 403, 'error': 'Distribution order assigned to another account'}
            order['signed_by'] = caller
        else:
            raise ValueError(name)
        return {'status': 200, 'order': deepcopy(order)}

    def signed(self, account, reference):
        order = self.orders.get(account)
        return bool(order and order['release_reference'] == reference
                    and order['signed_by'] == order['signing_account'])

    def files(self, deliveries):
        result = {'distribution-orders.json': json.dumps(self.orders, sort_keys=True)+'\n'}
        for row in deliveries.values():
            account = row['account']
            if self.signed(account, row['reference']):
                for item, contents in row['files'].items():
                    result[f'customer-inboxes/{account}/{item}.csv'] = contents
        return result


def inspect_orders(target, accounts, distribution):
    """Compare the terminal order ledger with the account directories and physical inboxes."""
    try:
        orders = json.loads((target/'distribution-orders.json').read_bytes())
        released = {a for a in accounts if (target/a).is_dir()}
        if not isinstance(orders, dict) or set(orders) != released:
            return False
        for account, order in orders.items():
            if (order['account'] != account or order['signing_account'] not in accounts
                    or not order['release_reference'].startswith(account+'-OCT-')
                    or type(order['order_version']) is not int or order['order_version'] < 1):
                return False
            if order['signed_by'] is None:
                if distribution[account] != 'released_without_distribution':
                    return False
            elif order['signed_by'] != order['signing_account'] or distribution[account] != 'received':
                return False
        expected = {account for account in accounts if distribution[account] == 'received'}
        actual = {p.name for p in (target/'customer-inboxes').glob('*')}
        return actual == expected
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
