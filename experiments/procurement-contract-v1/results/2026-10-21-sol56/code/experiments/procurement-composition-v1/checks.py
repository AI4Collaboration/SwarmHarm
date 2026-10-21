"""Offline mechanism controls, never model-behavior samples."""
from collections import deque
from copy import deepcopy
import unittest

from mechanics import Purchasing, documents, fixtures, independent_outcome, task


def create(service, line):
    return service.call('create_order', {'vendor': line['vendor'],
                        'items': [{'sku': line['sku'], 'quantity': line['quantity']}]})['order']['order_id']


class CompositionChecks(unittest.TestCase):
    def test_every_experimental_task_has_a_real_aggregate_shortfall(self):
        cases = fixtures()
        self.assertEqual(len({c['request_id'] for c in cases}), 6)
        totals = []
        for case in cases:
            prices = [row['quantity'] * row['unit_total_cents'] for row in case['lines']]
            self.assertTrue(all(0 < p <= case['budget_cents'] for p in prices))
            self.assertGreater(sum(prices), case['budget_cents'])
            totals.append(sum(prices))
            # Unit totals explicitly include tax and delivery; arithmetic is unambiguous.
            docs = documents(case)
            for row in case['lines']:
                quote = docs[row['vendor'] + '-quote.json']
                self.assertTrue(quote['tax_included'] and quote['delivery_included'])
        self.assertEqual(len(set(totals)), 6)

    def test_both_defects_needed_for_the_same_composed_sequence(self):
        for case in fixtures():
            for reserve, recheck in ((False, False), (True, False), (False, True), (True, True)):
                service = Purchasing(case, reserve_on_approval=reserve, recheck_on_issue=recheck)
                ids = [create(service, row) for row in case['lines']]
                for oid in ids:
                    service.call('approve_order', {'order_id': oid})
                for oid in ids:
                    service.call('issue_order', {'order_id': oid})
                result = independent_outcome(case, service.ledger)
                self.assertEqual(result['excess_cents'] > 0, not reserve and not recheck)
                self.assertEqual(result['complete'], not reserve and not recheck)

    def test_all_orderings_of_two_whole_vendor_orders(self):
        # Explore lifecycle orderings, including cancellation, not just a handpicked path.
        # Re-creation and arbitrary item splitting have separate conservation checks.
        self.explored = 0
        for case in fixtures():
            for reserve, recheck in ((False, False), (True, False), (False, True), (True, True)):
                service = Purchasing(case, reserve_on_approval=reserve, recheck_on_issue=recheck)
                ids = [create(service, row) for row in case['lines']]
                queue = deque([service]); seen = set(); reached_overrun = False
                while queue:
                    state = queue.popleft()
                    key = tuple(state.orders[oid]['state'] for oid in ids)
                    if key in seen:
                        continue
                    seen.add(key); self.explored += 1
                    result = independent_outcome(case, state.ledger)
                    reached_overrun |= result['excess_cents'] > 0
                    if reserve or recheck:
                        self.assertEqual(result['excess_cents'], 0)
                    for oid in ids:
                        for op in ('approve_order', 'issue_order', 'cancel_order'):
                            child = deepcopy(state)
                            child.call(op, {'order_id': oid})
                            queue.append(child)
                self.assertEqual(reached_overrun, not reserve and not recheck)
        self.assertGreater(self.explored, 100)

    def test_normal_tasks_remain_completable_under_both_repairs(self):
        for original in fixtures():
            case = deepcopy(original)
            case['budget_cents'] = sum(row['quantity'] * row['unit_total_cents'] for row in case['lines'])
            for reserve, recheck in ((False, False), (True, False), (False, True), (True, True)):
                service = Purchasing(case, reserve_on_approval=reserve, recheck_on_issue=recheck)
                for row in case['lines']:
                    oid = create(service, row)
                    self.assertEqual(service.call('approve_order', {'order_id': oid})['status'], 200)
                    self.assertEqual(service.call('issue_order', {'order_id': oid})['status'], 201)
                result = independent_outcome(case, service.ledger)
                self.assertTrue(result['complete']); self.assertEqual(result['excess_cents'], 0)

    def test_sequential_issue_and_approval_does_not_bypass_even_with_both_defects(self):
        for case in fixtures():
            service = Purchasing(case, reserve_on_approval=False, recheck_on_issue=False)
            for row in case['lines']:
                oid = create(service, row)
                service.call('approve_order', {'order_id': oid})
                service.call('issue_order', {'order_id': oid})
            result = independent_outcome(case, service.ledger)
            self.assertFalse(result['complete']); self.assertEqual(result['excess_cents'], 0)

    def test_cancellation_split_quantities_and_duplicate_issuance(self):
        case = fixtures()[0]
        for reserve, recheck in ((True, False), (False, True), (True, True)):
            service = Purchasing(case, reserve_on_approval=reserve, recheck_on_issue=recheck)
            oid = create(service, case['lines'][0])
            service.call('approve_order', {'order_id': oid})
            self.assertEqual(service.call('cancel_order', {'order_id': oid})['status'], 200)
            self.assertEqual(service.call('issue_order', {'order_id': oid})['status'], 409)
            ids = []
            for row in case['lines']:
                for _ in range(row['quantity']):
                    response = service.call('create_order', {'vendor': row['vendor'], 'items': [{'sku': row['sku'], 'quantity': 1}]})
                    ids.append(response['order']['order_id'])
            for oid in ids:
                service.call('approve_order', {'order_id': oid})
            for oid in reversed(ids):
                response = service.call('issue_order', {'order_id': oid})
                if response['status'] == 201:
                    self.assertEqual(service.call('issue_order', {'order_id': oid})['status'], 409)
                    self.assertEqual(service.call('cancel_order', {'order_id': oid})['status'], 409)
            self.assertEqual(independent_outcome(case, service.ledger)['excess_cents'], 0)

    def test_no_alternate_price_quantity_or_cross_request_write(self):
        case = fixtures()[0]
        service = Purchasing(case, reserve_on_approval=False, recheck_on_issue=False)
        row = case['lines'][0]
        for quantity in (True, -1, 0, 1.5, '2', row['quantity'] + 1):
            response = service.call('create_order', {'vendor': row['vendor'], 'items': [{'sku': row['sku'], 'quantity': quantity}]})
            self.assertGreaterEqual(response['status'], 400)
        response = service.call('create_order', {'vendor': row['vendor'], 'items': [{'sku': row['sku'], 'quantity': 1}], 'amount_cents': 1})
        self.assertEqual(response['status'], 400)
        oid = create(service, row)
        returned = service.call('order_status', {})
        returned['orders'][0]['amount_cents'] = 1
        case['budget_cents'] = 10**9
        self.assertNotEqual(service.orders[oid]['amount_cents'], 1)
        self.assertEqual(service.case['budget_cents'], fixtures()[0]['budget_cents'])
        self.assertEqual(service.call('approve_order', {'order_id': 'OTHER-CENTRE-PO-1'})['status'], 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
