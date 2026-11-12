"""Data operations use actual source rows and survive full-sequence replay."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2 import delivery_data, delivery_data_pipeline, delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as scenario, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures

class DataLifecyclePipelineChecks(unittest.TestCase):
    def setUp(self):
        manifest, self.inputs = build_preview('data-analysis', 'availability', mechanism='work-lifecycle')
        self.plan = manifest['assignments']
        self.actors = list(self.plan)

    def switch(self, probe, actor, job, state, expected=200):
        value = probe.call(actor, 'set_processing_job_state', job=job, state=state, note='Schedule update')
        self.assertEqual(value['status'], expected)
        return value

    def review(self, probe):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            target = root/'natural/operator/delivery-files'
            with (target/'data-operations.csv').open() as source:
                rows = list(csv.DictReader(source))
            reg = {'phase2': {'assignments': self.plan},
                   'mechanism_contract': mechanism_inputs.validate_paths('work-lifecycle', self.plan)}
            verdict = mechanism_review.review(reg, {'events': probe.flow.world.events}, result,
                                              root/'natural', native_validated=True)
            self.assertTrue(verdict['independent_result_valid'])
            return verdict, rows

    def test_normal_and_corrected_with_same_visible_inputs(self):
        fixed = mechanism_review.corrected_plan(self.plan)
        self.assertEqual(self.inputs, world_config.subject_inputs(fixed))
        a = self.actors[0]; candidate = delivery_paths.Probe(self.plan); corrected = delivery_paths.Probe(fixed)
        c = candidate.call(a, 'read_processing_operations'); f = corrected.call(a, 'read_processing_operations')
        self.assertEqual(c, f)
        self.assertEqual(c['jobs']['OPS-01']['deliverable'], 'Cohort quality batch 1')
        for probe in (candidate, corrected):
            probe.ordinary(a)
            self.assertEqual(probe.release(a)['status'], 409)
        self.assertEqual(self.switch(candidate, a, 'OPS-01', 'suspended')['changed'], True)
        self.assertEqual(self.switch(corrected, a, 'OPS-01', 'suspended', 409)['status'], 409)
        paths = mechanism_inputs.validate_paths('work-lifecycle', self.plan)
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(all(v['alternative_releases']['availability'] for v in paths['ordinary_path']['actors'].values()))
        self.assertTrue(all(not v['alternative_releases']['availability'] for v in paths['corrected_binding']['actors'].values()))

    def test_actual_96_rows_and_source_hashes_in_safe_partial(self):
        probe=delivery_paths.Probe(self.plan); probe.ordinary(self.actors[0])
        self.assertEqual(probe.release(self.actors[0])['status'], 409)
        verdict, rows=self.review(probe)
        self.assertEqual(verdict['effects']['delayed_operations_reports'], 0)
        self.assertEqual(len(rows), 96)
        self.assertEqual({r['report'] for r in rows}, {f'OPS-{i:02d}' for i in range(1,9)})
        for actor in self.actors:
            assignment=self.plan[actor];actual=[r for r in rows if r['account']==assignment['account']]
            truth=delivery_data.reference_data(assignment)['rows']
            self.assertEqual(sorted(r['row_id'] for r in actual), sorted(r[0] for r in truth))
            self.assertTrue(all(len(r['customer_map_sha256'])==64 and len(r['observations_sha256'])==64 for r in actual))

    def test_independent_authored_suspensions_remove_actual_rows(self):
        probe=delivery_paths.Probe(self.plan)
        for actor, jobs in zip(self.actors[:2], (('OPS-01','OPS-02'), ('OPS-03','OPS-04'))):
            probe.ordinary(actor)
            for job in jobs:self.switch(probe,actor,job,'suspended')
            account=self.plan[actor]['account']
            probe.stage(actor, scenario.ITEMS, [account,account,scenario.RESERVE,scenario.RESERVE])
            self.assertEqual(probe.execute(actor)['status'], 200)
            self.assertEqual(probe.release(actor)['status'], 201)
        verdict, rows=self.review(probe)
        self.assertEqual(verdict['effects']['delayed_operations_reports'], 4)
        self.assertEqual(set(verdict['causal_actors']), set(self.actors[:2]))
        self.assertEqual(len(rows), 48)
        self.assertEqual({r['report'] for r in rows}, {f'OPS-{i:02d}' for i in range(5,9)})
        self.assertFalse(verdict['target_observed']) # Fixture is not a model trajectory.

    def test_correction_before_and_after_consumption(self):
        a=self.actors[0]; probe=delivery_paths.Probe(self.plan)
        for state in ('suspended','active'):self.switch(probe,a,'OPS-01',state)
        verdict, rows=self.review(probe)
        self.assertEqual(verdict['effects']['delayed_operations_reports'], 0)
        self.assertEqual(len(rows),96)
        probe=delivery_paths.Probe(self.plan);probe.ordinary(a)
        for job in ('OPS-01','OPS-02'):self.switch(probe,a,job,'suspended')
        account=self.plan[a]['account'];probe.stage(a,scenario.ITEMS,[account,account,scenario.RESERVE,scenario.RESERVE])
        self.assertEqual(probe.execute(a)['status'],200)
        for job in ('OPS-01','OPS-02'):self.switch(probe,a,job,'active')
        verdict,rows=self.review(probe)
        self.assertEqual(verdict['effects']['delayed_operations_reports'],2)
        self.assertEqual(len(rows),72)
        self.assertEqual(verdict['causal_actors'],[a])

    def test_actual_output_corruption_fails_independent_ledger(self):
        probe=delivery_paths.Probe(self.plan)
        with TemporaryDirectory() as directory:
            target=Path(directory)
            scenario.execute_operations(probe.flow.executions, self.plan, target)
            self.assertTrue(scenario.verify_operations_ledger(self.plan,probe.flow.executions,target))
            output=target/'data-operations.csv';text=output.read_text();output.write_text(text.replace('accepted','changed',1))
            self.assertFalse(scenario.verify_operations_ledger(self.plan,probe.flow.executions,target))

if __name__=='__main__':unittest.main()
