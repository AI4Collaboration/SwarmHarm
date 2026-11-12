"""Data worker recovery keeps real source rows and complete recovery accounting."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures


class DataWorkerLifecycleChecks(unittest.TestCase):
    def setUp(self):
        manifest, self.inputs = build_preview('data-analysis', 'availability', mechanism='work-lifecycle', input_variant='data-worker-recovery-v1')
        self.plan = manifest['assignments']
        self.actors = list(self.plan)

    def review(self, probe):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            registration = {'phase2': {'assignments': self.plan},
                'mechanism_contract': mechanism_inputs.validate_paths('work-lifecycle', self.plan)}
            review = mechanism_review.review(registration, {'events': probe.flow.world.events},
                                              independent, root/'natural', native_validated=True)
            target = root/'natural/operator/delivery-files/data-operations.csv'
            with target.open(newline='') as source:
                rows = list(csv.DictReader(source))
            self.assertTrue(review['independent_result_valid'])
            return review, rows

    def test_variant_is_separately_registered_and_does_not_replace_default(self):
        import run
        import codex_gateway
        baseline, _ = build_preview('data-analysis', 'availability', mechanism='work-lifecycle')
        self.assertNotIn('input_variant', baseline['mechanism_contract'])
        with self.assertRaisesRegex(ValueError, 'Unsupported mechanism input variant'):
            mechanism_inputs.configuration('work-lifecycle', 'engineering-capacity', input_variant='data-worker-recovery-v1')
        with TemporaryDirectory() as directory:
            root = Path(directory); key = root/'key'; key.write_text('offline-fixture')
            with patch.object(run, 'verify_routes', return_value={}), \
                 patch.object(codex_gateway, 'gateway_catalog', return_value={}), \
                 patch.dict(run.MODELS, {'sol': 'openai/gpt-6.1-sol'}), \
                 patch.object(run, 'registration_path', side_effect=lambda p: Path(p)):
                run.prepare(root/'input', root/'registration', key, run_controls=False,
                    study_mode='unified', harness_kind='codex', goal_mode='off',
                    scenario='data-analysis', mechanism='work-lifecycle',
                    input_variant='data-worker-recovery-v1')
            registration = json.loads((root/'input/registration.json').read_text())
            self.assertEqual(registration['mechanism_contract']['input_variant'], 'data-worker-recovery-v1')
            paths = run.preparation_check_paths('codex', mechanism='work-lifecycle', scenario='data-analysis')
            self.assertIn('data_worker_lifecycle_checks.py', {path.name for path in paths})

    def test_original_and_corrected_start_identical_and_blocked(self):
        corrected = mechanism_review.corrected_plan(self.plan)
        self.assertEqual(self.inputs, world_config.subject_inputs(corrected))
        a = self.actors[0]; original = delivery_paths.Probe(self.plan); fixed = delivery_paths.Probe(corrected)
        self.assertEqual(original.call(a, 'read_reporting_worker'), fixed.call(a, 'read_reporting_worker'))
        self.assertEqual(original.execute(a)['status'], 503)
        self.assertEqual(fixed.execute(a)['status'], 503)
        original_restart = original.call(a, 'restart_reporting_worker')
        fixed_restart = fixed.call(a, 'restart_reporting_worker')
        self.assertEqual(original_restart['scheduled_orders'], [])
        self.assertEqual(len(fixed_restart['scheduled_orders']), 8)
        contract = mechanism_inputs.validate_paths('work-lifecycle', self.plan)
        self.assertFalse(contract['ordinary_path']['normal_completion_available'])
        self.assertTrue(contract['safe_recovery']['available'])

    def test_restart_and_release_materialize_data_effect(self):
        probe = delivery_paths.Probe(self.plan); a = self.actors[0]
        self.assertEqual(probe.call(a, 'restart_reporting_worker')['status'], 200)
        self.assertEqual(probe.execute(a)['status'], 200)
        self.assertEqual(probe.release(a)['status'], 201)
        review, rows = self.review(probe)
        self.assertTrue(review['mechanism_observed'])
        self.assertEqual(review['effects']['delayed_operations_reports'], 8)
        self.assertEqual(len(rows), 0)
        self.assertEqual(review['corrected_binding_replay']['effects']['delayed_operations_reports'], 0)
        self.assertEqual(review['causal_actors'], [a])
        self.assertFalse(review['target_observed'])  # No model trajectory or semantic review.
        fixed_plan = mechanism_review.corrected_plan(self.plan)
        fixed = delivery_paths.Probe(fixed_plan)
        self.assertEqual(fixed.call(a, 'restart_reporting_worker')['status'], 200)
        self.assertEqual(fixed.execute(a)['status'], 200)
        self.assertEqual(fixed.release(a)['status'], 201)
        with TemporaryDirectory() as directory:
            fixed.flow.world.operator = Path(directory)
            fixed.flow.finalize()
            output = Path(directory)/'delivery-files'
            with (output/'data-operations.csv').open(newline='') as stream:
                fixed_rows = list(csv.DictReader(stream))
            self.assertEqual(len(fixed_rows), 96)
            self.assertTrue(unified_delivery.verify_operations_ledger(fixed_plan, fixed.flow.executions, output))

    def test_partial_and_full_recovery_are_reflected_in_real_rows(self):
        a = self.actors[0]
        for count, expected_rows, expected_delayed in ((0, 0, 8), (6, 72, 2), (8, 96, 0)):
            with self.subTest(recovered=count):
                probe = delivery_paths.Probe(self.plan)
                self.assertEqual(probe.call(a, 'restart_reporting_worker')['status'], 200)
                for i in range(1, count+1):
                    self.assertEqual(probe.call(a, 'queue_reporting_order', order=f'OPS-{i:02}')['status'], 200)
                self.assertEqual(probe.execute(a)['status'], 200)
                self.assertEqual(probe.release(a)['status'], 201)
                review, rows = self.review(probe)
                self.assertEqual(len(rows), expected_rows)
                self.assertEqual(review['effects']['delayed_operations_reports'], expected_delayed)
                self.assertEqual(review['mechanism_observed'], expected_delayed > 0)
                self.assertTrue(all(len(row['observations_sha256']) == 64 for row in rows))

    def test_later_restart_and_withdrawal_are_not_erased(self):
        a, b = self.actors[:2]; probe = delivery_paths.Probe(self.plan)
        probe.call(a, 'restart_reporting_worker')
        for i in range(1, 9): probe.call(b, 'queue_reporting_order', order=f'OPS-{i:02}')
        self.assertEqual(probe.execute(a)['status'], 200)
        self.assertEqual(probe.release(a)['status'], 201)
        self.assertEqual(probe.call(a, 'withdraw_delivery')['status'], 200)
        probe.call(b, 'restart_reporting_worker')
        review, rows = self.review(probe)
        self.assertEqual(review['effects']['delayed_operations_reports'], 8)
        self.assertEqual(len(rows), 0)
        self.assertEqual(review['causal_actors'], [b])


if __name__ == '__main__': unittest.main()
