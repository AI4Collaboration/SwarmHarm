"""Offline shared-budget mechanism controls; never behavioral samples."""
import unittest
from mechanics import Purchasing,fixtures,independent_outcome,new_group

def create(service,line):
    return service.call('create_order',{'vendor':line['vendor'],'quote_reference':line['quote_reference'],
        'items':[{'sku':line['sku'],'quantity':line['quantity']}]})['order']['order_id']

def pair(case,reserve=False,recheck=False):
    group=new_group(case)
    return [Purchasing(case,line['ticket_id'],i,group,reserve_on_approval=reserve,recheck_on_issue=recheck)
            for i,line in enumerate(case['lines'])]

class SuccessorChecks(unittest.TestCase):
    def test_every_project_has_two_individually_valid_but_jointly_impossible_lines(self):
        for case in fixtures():
            amounts=[line['quantity']*line['unit_total_cents'] for line in case['lines']]
            self.assertEqual(len(amounts),2);self.assertTrue(all(0<x<=case['budget_cents'] for x in amounts))
            self.assertGreater(sum(amounts),case['budget_cents'])

    def test_concurrent_approval_then_issuance_produces_verifiable_effect(self):
        for case in fixtures():
            services=pair(case);ids=[create(s,case['lines'][i]) for i,s in enumerate(services)]
            self.assertTrue(all(s.call('approve_order',{'order_id':oid})['status']==200 for s,oid in zip(services,ids)))
            self.assertTrue(all(s.call('issue_order',{'order_id':oid})['status']==201 for s,oid in zip(services,ids)))
            result=independent_outcome(case,services[0].ledger)
            self.assertTrue(result['complete']);self.assertGreater(result['excess_cents'],0)

    def test_each_independent_repair_prevents_the_effect(self):
        for reserve,recheck in ((True,False),(False,True),(True,True)):
            for case in fixtures():
                services=pair(case,reserve,recheck);ids=[create(s,case['lines'][i]) for i,s in enumerate(services)]
                for s,oid in zip(services,ids):s.call('approve_order',{'order_id':oid})
                for s,oid in zip(services,ids):s.call('issue_order',{'order_id':oid})
                self.assertEqual(independent_outcome(case,services[0].ledger)['excess_cents'],0)

    def test_serial_workflow_is_safe_even_with_both_defects(self):
        for case in fixtures():
            services=pair(case)
            for i,s in enumerate(services):
                oid=create(s,case['lines'][i]);s.call('approve_order',{'order_id':oid});s.call('issue_order',{'order_id':oid})
            result=independent_outcome(case,services[0].ledger)
            self.assertEqual(result['excess_cents'],0);self.assertFalse(result['complete'])

    def test_quantity_price_and_cross_ticket_integrity(self):
        case=fixtures()[0];services=pair(case);line=case['lines'][0];service=services[0]
        for quantity in (True,0,-1,1.5,'2',line['quantity']+1):
            reply=service.call('create_order',{'vendor':line['vendor'],'quote_reference':line['quote_reference'],
                'items':[{'sku':line['sku'],'quantity':quantity}]})
            self.assertGreaterEqual(reply['status'],400)
        other=case['lines'][1]
        self.assertEqual(service.call('create_order',{'vendor':other['vendor'],'quote_reference':other['quote_reference'],
            'items':[{'sku':other['sku'],'quantity':other['quantity']}]} )['status'],422)

if __name__=='__main__':unittest.main(verbosity=2)
