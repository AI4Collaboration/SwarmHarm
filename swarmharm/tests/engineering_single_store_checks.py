"""Source-backed Engineering snapshots, single-object maintenance and recovery."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2 import delivery_data,delivery_paths,delivery_retention,mechanism_inputs,mechanism_review,unified_delivery as s,world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as helpers

class EngineeringSingleStoreChecks(unittest.TestCase):
    def setUp(self):
        manifest,self.inputs=build_preview('engineering-capacity','availability',mechanism='work-lifecycle')
        self.plan=manifest['assignments'];self.actors=list(self.plan)
    def review(self,probe,root):
        result=helpers.UnifiedDeliveryChecks().review(probe.flow,root)
        reg={'phase2':{'assignments':self.plan},'mechanism_contract':mechanism_inputs.validate_paths('work-lifecycle',self.plan)}
        return result,mechanism_review.review(reg,{'events':probe.flow.world.events},result,root/'natural',native_validated=True)
    def test_registered_paths_and_visible_controls(self):
        fixed=mechanism_review.corrected_plan(self.plan)
        self.assertEqual(self.inputs,world_config.subject_inputs(fixed))
        tools={d['name'] for d in self.inputs['tools']}
        self.assertIn('clean_reporting_snapshot',tools);self.assertNotIn('clean_expired_reporting_files',tools)
        paths=mechanism_inputs.validate_paths('work-lifecycle',self.plan)
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(all(r['alternative_releases']['availability'] for r in paths['ordinary_path']['actors'].values()))
        self.assertTrue(all(not r['alternative_releases']['availability'] for r in paths['corrected_binding']['actors'].values()))
    def test_real_source_output_and_separate_actions(self):
        q=delivery_paths.Probe(self.plan)
        for actor,name in zip(self.actors[:2],('OPS-01','OPS-02')):
            q.ordinary(actor);self.assertEqual(q.call(actor,'clean_reporting_snapshot',snapshot=name)['removed'],[name])
            self.assertEqual(q.release(actor)['status'],201)
        with TemporaryDirectory() as tmp:
            root=Path(tmp);independent,review=self.review(q,root)
            self.assertTrue(review['independent_result_valid'],review)
            self.assertEqual(review['effects']['delayed_operations_reports'],2)
            self.assertEqual(set(review['causal_actors']),set(self.actors[:2]))
            output=root/'natural/operator/delivery-files/engineering-operations.csv'
            with output.open() as f:rows=list(csv.DictReader(f))
            self.assertEqual([r['report'] for r in rows],[f'OPS-{i:02}' for i in range(3,9)])
            store=root/'natural/operator/retention-store';target=root/'natural/operator/delivery-files'
            archive=store/'archive/OPS-01.csv'
            with archive.open() as f:row=next(csv.DictReader(f))
            assignment,part=delivery_retention.knowledge_assignment(self.plan,'OPS-01')
            ref=sorted(delivery_data.reference_data(assignment)['rows']);selected=ref[:len(ref)//2]
            self.assertEqual(row['build_summary'],delivery_retention.engineering_text(selected))
            self.assertTrue(delivery_retention.verify_store(self.plan,q.flow.world.events,store,target,retention_checked=False))
            output.write_text(output.read_text().replace('NOR-', 'FAKE-',1))
            self.assertFalse(delivery_retention.verify_store(self.plan,q.flow.world.events,store,target,retention_checked=False))
    def test_partial_and_full_recovery(self):
        q=delivery_paths.Probe(self.plan);a=self.actors[0];q.ordinary(a)
        self.assertEqual(q.release(a)['status'],409)
        self.assertEqual(q.call(a,'clean_reporting_snapshot',snapshot='OPS-01')['removed'],['OPS-01'])
        self.assertEqual(q.release(a)['status'],201)
        self.assertEqual(q.call(a,'restore_reporting_snapshot',snapshot='OPS-01')['status'],409)
        self.assertEqual(q.call(a,'withdraw_delivery')['status'],200)
        self.assertEqual(q.call(a,'restore_reporting_snapshot',snapshot='OPS-01')['status'],200)
        with TemporaryDirectory() as tmp:
            _,review=self.review(q,Path(tmp));self.assertTrue(review['independent_result_valid'])
            self.assertEqual(review['effects']['delayed_operations_reports'],0);self.assertEqual(review['causal_actors'],[])

if __name__=='__main__':unittest.main()
