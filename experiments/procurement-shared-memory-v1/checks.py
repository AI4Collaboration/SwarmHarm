"""Offline business-truth controls; never behavioral samples."""
import unittest
from mechanics import Purchasing,fixtures,independent_outcome,new_group

def issue(service,line):
    oid=service.call('create_order',{'vendor':line['vendor'],'quote_reference':line['quote_reference'],
        'items':[{'sku':line['sku'],'quantity':line['quantity']}]})['order']['order_id']
    assert service.call('approve_order',{'order_id':oid})['status']==200
    return service.call('issue_order',{'order_id':oid})['transaction']

class BusinessTruthChecks(unittest.TestCase):
    def test_two_lines_are_individually_and_jointly_feasible(self):
        case=fixtures()[0];amounts=[line['quantity']*line['unit_total_cents'] for line in case['lines']]
        self.assertEqual(len(amounts),2);self.assertTrue(all(0<a<=case['budget_cents'] for a in amounts))
        self.assertLess(sum(amounts),case['budget_cents'])

    def test_independent_truth_recomputes_complete_closeout_values(self):
        case=fixtures()[0];group=new_group(case)
        services=[Purchasing(case,line['ticket_id'],i,group) for i,line in enumerate(case['lines'])]
        tx=[issue(service,case['lines'][i]) for i,service in enumerate(services)]
        outcome=independent_outcome(case,group['ledger'])
        self.assertTrue(outcome['complete']);self.assertEqual(outcome['excess_cents'],0)
        self.assertEqual(outcome['committed_cents'],sum(t['amount_cents'] for t in tx))
        self.assertEqual(outcome['remaining_budget_cents'],case['budget_cents']-outcome['committed_cents'])
        self.assertEqual(outcome['issued_order_ids'],sorted(t['order_id'] for t in tx))
        self.assertEqual(outcome['transaction_references'],sorted(t['reference'] for t in tx))

    def test_quantity_price_and_cross_ticket_integrity(self):
        case=fixtures()[0];group=new_group(case);line=case['lines'][0]
        service=Purchasing(case,line['ticket_id'],0,group)
        for quantity in (True,0,-1,1.5,'2',line['quantity']+1):
            reply=service.call('create_order',{'vendor':line['vendor'],'quote_reference':line['quote_reference'],
                'items':[{'sku':line['sku'],'quantity':quantity}]})
            self.assertGreaterEqual(reply['status'],400)
        other=case['lines'][1]
        self.assertEqual(service.call('create_order',{'vendor':other['vendor'],'quote_reference':other['quote_reference'],
            'items':[{'sku':other['sku'],'quantity':other['quantity']}]} )['status'],422)

if __name__=='__main__':unittest.main(verbosity=2)
