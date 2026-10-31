"""Business reachability controls do not establish native communication."""
import json
import unittest

from phase1 import engineering_carrier_controls as controls, engineering_carriers, fixture_ids, lab, schedule


class EngineeringCarrierFilingChecks(unittest.TestCase):
    def setUp(self):
        ids = iter(f'job-{i}' for i in range(4))
        self.plan = schedule.compile_plan(scenario='engineering-capacity', id_factory=ids.__next__)[0]['natural']
        fixture_ids.register(self.plan)

    def check_kind(self, kind):
        result = controls.evaluate_pair(self.plan, kind)
        self.assertFalse(result['ready'])
        for name, branch in result['branches'].items():
            self.assertEqual(branch['ordinary_filed'], 4)
            self.assertEqual(branch['final_filed'], 4 if name.endswith('-repaired') else 8)
            self.assertEqual(branch['total_assigned'], 8)
            self.assertTrue(branch['subject_surfaces_identical'])
            self.assertEqual(branch['invalid_source_statuses'], [422] * 4)
            self.assertTrue(all(n <= engineering_carriers.MAX_BUILDS_PER_ACTOR
                                for n in branch['builds_per_actor'].values()))
            # Operator source locators are discovered by ordinary calls. They
            # must never be planted into the initial files or model input.
            for actor, item in self.plan.items():
                visible = json.dumps(lab.initial(self.plan, actor))
                visible += '\n'.join(lab.DECODE(v) for v in lab.files(item, actor).values())
                for scope in branch['source_scopes'].values():
                    self.assertNotIn(scope, visible)

    def test_artifact_path_completes_source_backed_filing_only_through_defect(self):
        self.check_kind('data_object')

    def test_real_compiler_reports_complete_filing_only_through_misdelivery(self):
        self.check_kind('message_transport')

    def test_actual_lock_states_complete_filing_only_through_shared_lock_identity(self):
        self.check_kind('synchronization')

    def test_resource_witness_remains_unestablished_and_cannot_be_silently_substituted(self):
        with self.assertRaisesRegex(ValueError, 'No full-filing witness'):
            controls.evaluate_pair(self.plan, 'execution_resource')


if __name__ == '__main__':
    unittest.main()
