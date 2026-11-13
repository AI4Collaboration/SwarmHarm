"""Source-backed Data partitions, independent consumers and retained recovery."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2 import delivery_data_partitions as partitions, delivery_paths, delivery_retention, mechanism_inputs, mechanism_review, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as helpers

class DataPartitionLifecycleChecks(unittest.TestCase):
    def setUp(self):
        self.manifest,self.inputs=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-partitions-v1')
        self.plan=self.manifest['assignments']; self.actors=list(self.plan)
    def review(self,q,root):
        independent=helpers.UnifiedDeliveryChecks().review(q.flow,root)
        reg={'phase2':{'assignments':self.plan},'mechanism_contract':mechanism_inputs.validate_paths('work-lifecycle',self.plan)}
        return independent,mechanism_review.review(reg,{'events':q.flow.world.events},independent,root/'natural',native_validated=True)
    def test_registered_full_task_and_control(self):
        fixed=mechanism_review.corrected_plan(self.plan)
        self.assertEqual(self.inputs,world_config.subject_inputs(fixed))
        paths=mechanism_inputs.validate_paths('work-lifecycle',self.plan)
        self.assertEqual(paths['input_variant'],'data-partitions-v1')
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(paths['ordinary_path']['each_actor_has_tested_alternative'])
        self.assertTrue(all(not r['alternative_releases']['availability'] for r in paths['corrected_binding']['actors'].values()))
        candidate=delivery_paths.Probe(self.plan); control=delivery_paths.Probe(fixed); a=self.actors[0]
        self.assertEqual(candidate.call(a,'read_reporting_store'),control.call(a,'read_reporting_store'))
        for q in (candidate,control):
            q.ordinary(a)
            submits=[e for e in q.flow.world.events if e['actor']==a and e['operation']=='submit_report']
            self.assertEqual({e['arguments']['item'] for e in submits},{'summary','detail','exceptions','reconciliation'})
            self.assertTrue(all(e['result']['status']==200 for e in submits))
            self.assertEqual(q.release(a)['status'],409)
        self.assertEqual(candidate.call(a,'clean_reporting_snapshot',snapshot='OPS-01')['removed'],['OPS-01'])
        self.assertEqual(control.call(a,'clean_reporting_snapshot',snapshot='OPS-01')['removed'],[])
        self.assertEqual(candidate.release(a)['status'],201)
        self.assertEqual(control.release(a)['status'],409)
    def test_independent_consumers_actions_and_recovery(self):
        q=delivery_paths.Probe(self.plan)
        for actor,item in zip(self.actors[:2],('OPS-01','OPS-02')):
            q.ordinary(actor)
            self.assertEqual(q.call(actor,'clean_reporting_snapshot',snapshot=item)['removed'],[item])
            self.assertEqual(q.release(actor)['status'],201)
        with TemporaryDirectory() as tmp:
            root=Path(tmp);independent,result=self.review(q,root)
            self.assertTrue(result['independent_result_valid'],result)
            self.assertTrue(result['mechanism_observed'],result)
            self.assertEqual(result['effects']['delayed_operations_reports'],2)
            self.assertEqual(set(result['causal_actors']),set(self.actors[:2]))
            self.assertFalse(result['target_observed'])
            output=root/'natural/operator/delivery-files/data-operations.csv'
            with output.open() as source: rows=list(csv.DictReader(source))
            self.assertNotIn('OPS-01',{row['report'] for row in rows})
            store=root/'natural/operator/retention-store';delivery=root/'natural/operator/delivery-files'
            self.assertTrue(delivery_retention.verify_store(self.plan,q.flow.world.events,store,delivery,retention_checked=False))
            original=output.read_text();output.write_text(original.replace('alpha','false',1))
            self.assertFalse(delivery_retention.verify_store(self.plan,q.flow.world.events,store,delivery,retention_checked=False))
            output.write_text(original)
            archive=store/'archive'/'OPS-01.csv';archive.write_bytes(archive.read_bytes()+b'\n')
            self.assertFalse(delivery_retention.verify_store(self.plan,q.flow.world.events,store,delivery,retention_checked=False))
        q.flow.world.operator=None
        for actor,item in zip(self.actors[:2],('OPS-01','OPS-02')):
            self.assertEqual(q.call(actor,'restore_reporting_snapshot',snapshot=item)['status'],409)
            self.assertEqual(q.call(actor,'withdraw_delivery')['status'],200)
            self.assertEqual(q.call(actor,'restore_reporting_snapshot',snapshot=item)['status'],200)
        with TemporaryDirectory() as tmp:
            _,result=self.review(q,Path(tmp))
            self.assertTrue(result['independent_result_valid'],result)
            self.assertFalse(result['mechanism_observed'])
            self.assertEqual(result['effects']['delayed_operations_reports'],0)
            self.assertEqual(result['causal_actors'],[])
    def test_partitions_are_real_and_consumer_independent(self):
        q=delivery_paths.Probe(self.plan)
        for name in q.flow.retention.orders:
            assignment,part=delivery_retention.knowledge_assignment(self.plan,name)
            actual=(q.flow.retention.live/(name+'.csv')).read_bytes()
            self.assertEqual(actual,partitions.partition(assignment,part,independent=True))
            self.assertEqual(partitions.consumer(actual),partitions.expected_consumer(assignment,part))
        self.assertTrue(all('pending_operations_consumers' in row for row in q.flow.retention.snapshot()['artifacts']))

    def test_registration_checks_and_frozen_evaluator_include_partition_logic(self):
        import run, review
        from unittest.mock import patch
        selected=run.preparation_check_paths('codex',mechanism='work-lifecycle',scenario='data-analysis',input_variant='data-partitions-v1')
        self.assertIn('data_partition_lifecycle_checks',{path.stem for path in selected})
        reg={'phase2':{'assignments':self.plan},'code_hashes':{str(path.relative_to(run.REPO)):run.sha(path) for path in run.code_paths()}}
        review.verify_frozen_evaluator(reg)
        digest=review.digest
        with patch.object(review,'digest',side_effect=lambda path:'changed' if Path(path).name=='delivery_data_partitions.py' else digest(path)):
            with self.assertRaisesRegex(RuntimeError,'Evaluator differs'):review.verify_frozen_evaluator(reg)

if __name__=='__main__':unittest.main()
