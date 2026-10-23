"""Independent-review controls; no model calls."""
import unittest
import live_checks,review

class ReviewChecks(unittest.TestCase):
    def test_complete_offline_chain_passes_all_phase1_gates(self):
        plan=live_checks.plan();world=live_checks.lab.World(plan)
        try:
            records=[live_checks.complete_line(world,'writer-0',0),live_checks.complete_line(world,'writer-1',1)]
            listed=world.call('closer',20,'list_reconciliations',{})['records']
            read=[world.call('closer',21+i,'read_reconciliation',{'record_id':row['record_id']})['record'] for i,row in enumerate(listed)]
            case=live_checks.lab.case_for(plan['closer']);truth=live_checks.mechanics.independent_outcome(case,world.group_ledger(plan['closer']))
            world.call('closer',30,'submit_project_closeout',{'project_id':case['group_id'],
                'supporting_record_ids':[r['record_id'] for r in read],
                'purchase_order_references':[ref for r in read for ref in r['purchase_order_references']],
                'total_committed_cents':sum(r['committed_cents'] for r in read),
                'remaining_budget_cents':truth['remaining_budget_cents']})
            states={'writer-0':{'status':'completed','finished_at':'2026-10-23T10:00:00+00:00'},
                'writer-1':{'status':'completed','finished_at':'2026-10-23T10:00:01+00:00'},
                'closer':{'status':'completed','started_at':'2026-10-23T10:00:02+00:00'}}
            reg={'plan':{'natural':plan}};result=review.assess(reg,world.snapshot(),states)
            self.assertTrue(result['phase1_passed']);self.assertTrue(all(result['gates'].values()))
        finally:world.close()

if __name__=='__main__':unittest.main(verbosity=2)
