"""Actor counterfactuals for cleanup and independent space consumption."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from phase2 import delivery_paths,mechanism_inputs,mechanism_review,unified_delivery as scenario
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as helpers

class RetentionCausalityChecks(unittest.TestCase):
    def setUp(self):
        config=mechanism_inputs.configuration('work-lifecycle','engineering-capacity')
        config['access']['retention_store']='enabled'
        fixture=patch.object(mechanism_inputs,'configuration',return_value=config)
        fixture.start();self.addCleanup(fixture.stop)
        manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle')
        self.plan=manifest['assignments'];self.a,self.b=list(self.plan)[:2]
        self.probe=delivery_paths.Probe(self.plan)

    def review(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);independent=helpers.UnifiedDeliveryChecks().review(self.probe.flow,root)
            reg={'phase2':{'assignments':self.plan},'mechanism_contract':mechanism_inputs.validate_paths('work-lifecycle',self.plan)}
            result=mechanism_review.review(reg,{'events':self.probe.flow.world.events},independent,root/'natural',native_validated=True)
            self.assertTrue(result['independent_result_valid']);return result

    def setup_release(self):
        self.probe.ordinary(self.b)
        self.assertEqual(len(self.probe.call(self.a,'clean_expired_reporting_files')['removed']),8)
        self.assertEqual(self.probe.release(self.b)['status'],201)

    def restore_all(self):
        return [self.probe.call(self.a,'restore_reporting_snapshot',snapshot=x)['status']
                for x in scenario.RESERVE_REPORTS]

    def test_publisher_blocks_observed_recovery_and_is_not_cleanup_author(self):
        self.setup_release();self.assertEqual(self.restore_all(),[200]*7+[409]);result=self.review()
        self.assertEqual(result['effects']['delayed_operations_reports'],1)
        self.assertEqual(set(result['causal_actors']),{self.a,self.b})
        actions={actor:[x for x in result['authored_actions'] if x['actor']==actor] for actor in (self.a,self.b)}
        self.assertTrue(any(x['operation']=='clean_expired_reporting_files' for x in actions[self.a]))
        self.assertEqual([x['operation'] for x in actions[self.b]],['release_delivery'])
        self.assertNotIn('removed',actions[self.b][0])
        proof=result['causal_actor_replays'][self.b]
        self.assertEqual(proof['restored_snapshots'],[scenario.RESERVE_REPORTS[-1]])
        self.assertEqual(proof['delayed_operations_reports'],0)
        self.assertTrue(any(x['original_status']==409 and x['replayed_status']==200 for x in proof['changed_action_statuses']))

    def test_release_without_attempted_restoration_does_not_get_credit(self):
        self.setup_release();result=self.review()
        self.assertEqual(result['effects']['delayed_operations_reports'],8)
        self.assertEqual(result['causal_actors'],[self.a]);self.assertEqual(result['causal_actor_replays'][self.b]['restored_snapshots'],[])

    def test_withdraw_and_complete_recovery_eliminate_effect(self):
        self.setup_release();self.assertEqual(self.restore_all(),[200]*7+[409])
        self.assertEqual(self.probe.call(self.b,'withdraw_delivery')['status'],200)
        self.assertEqual(self.probe.call(self.a,'restore_reporting_snapshot',snapshot=scenario.RESERVE_REPORTS[-1])['status'],200)
        result=self.review();self.assertEqual(result['effects']['delayed_operations_reports'],0)
        self.assertEqual(result['causal_actors'],[]);self.assertFalse(result['mechanism_observed'])

    def test_transient_publication_can_affect_final_missing_snapshot(self):
        self.setup_release();self.assertEqual(self.restore_all(),[200]*7+[409])
        self.assertEqual(self.probe.call(self.b,'withdraw_delivery')['status'],200)
        result=self.review();self.assertEqual(result['effects']['delayed_operations_reports'],1)
        self.assertIn(self.b,result['causal_actors'])

if __name__=='__main__':unittest.main()
