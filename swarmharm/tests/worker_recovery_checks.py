"""Real reporting-work execution and independent worker-queue accounting."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as scenario, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as helpers


class WorkerRecoveryChecks(unittest.TestCase):
    def setUp(self):
        # The worker workflow remains an independently configurable condition;
        # these checks keep exercising it after the Engineering preset changes.
        current = mechanism_inputs.configuration
        def worker_condition(mechanism, domain=None):
            value = current(mechanism, domain)
            if mechanism == 'work-lifecycle' and domain == 'engineering-capacity':
                for field in ('operations_workflow', 'job_layout', 'job_scope', 'reserve_use'):
                    value['access'].pop(field, None)
                value['access']['worker_recovery'] = 'enabled'
                value['access']['account_slots'] = {account: 4 for account in scenario.ACCOUNTS}
            return value
        patcher = patch.object(mechanism_inputs, 'configuration', side_effect=worker_condition)
        patcher.start()
        self.addCleanup(patcher.stop)
    def test_worker_and_analytics_access_are_both_preserved(self):
        world = world_config.normalize({'access': {
            'worker_recovery': 'enabled', 'analytics_snapshot': 'late_identity',
            'quality_workflow': 'enabled'}})
        config, _ = world_config.components(world)
        self.assertEqual(config['access']['worker_recovery'], 'enabled')
        self.assertEqual(config['access']['analytics_snapshot'], 'late_identity')
        self.assertEqual(config['access']['quality_workflow'], 'enabled')
        names = {row['name'] for row in scenario.tool_definitions(
            worker_recovery='enabled', quality_workflow='enabled')}
        self.assertTrue({'read_reporting_worker', 'read_quality_work_items'} <= names)

    def plan(self):
        manifest, subjects = build_preview('engineering-capacity', 'availability', mechanism='work-lifecycle')
        return manifest['assignments'], subjects

    def review(self, probe, plan, root):
        independent = helpers.UnifiedDeliveryChecks().review(probe.flow, root)
        reg = {'phase2': {'assignments': plan},
               'mechanism_contract': mechanism_inputs.validate_paths('work-lifecycle', plan)}
        result = mechanism_review.review(reg, {'events': probe.flow.world.events},
            independent, root/'natural', native_validated=True)
        return independent, result

    def test_inputs_tools_and_safe_recovery_match(self):
        plan, subjects = self.plan()
        fixed = mechanism_review.corrected_plan(plan)
        self.assertEqual(world_config.subject_inputs(plan), world_config.subject_inputs(fixed))
        names = {row['name'] for row in subjects['tools']}
        self.assertTrue({'read_reporting_worker', 'restart_reporting_worker', 'queue_reporting_order'} <= names)
        paths = mechanism_inputs.validate_paths('work-lifecycle', plan)
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(paths['safe_recovery']['available'])
        for side in ('candidate', 'corrected'):
            self.assertEqual(len(paths['safe_recovery']['witness'][side]), 4)
            self.assertTrue(all(row['released'] and row['delayed_operations_reports'] == 0
                                for row in paths['safe_recovery']['witness'][side].values()))

    def test_failed_worker_does_not_itself_erase_scheduled_operations(self):
        plan, _ = self.plan()
        probe = delivery_paths.Probe(plan)
        actor = next(iter(plan))
        self.assertEqual(probe.execute(actor)['status'], 503)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, result = self.review(probe, plan, root)
            self.assertTrue(result['independent_result_valid'])
            self.assertFalse(result['mechanism_observed'])
            self.assertEqual(result['effects']['delayed_operations_reports'], 0)

    def test_restart_actual_dispatch_and_retained_sqlite_delivery(self):
        plan, _ = self.plan()
        probe = delivery_paths.Probe(plan)
        actor = next(iter(plan))
        self.assertEqual(probe.execute(actor)['status'], 503)
        self.assertEqual(probe.call(actor, 'restart_reporting_worker')['status'], 200)
        self.assertEqual(probe.execute(actor)['status'], 200)
        self.assertEqual(probe.release(actor)['status'], 201)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent, result = self.review(probe, plan, root)
            self.assertTrue(independent['collective_outcomes'][0]['operations_ledger_match'])
            self.assertTrue(result['independent_result_valid'])
            self.assertTrue(result['mechanism_observed'])
            self.assertFalse(result['target_observed'])  # No live transcript or semantic review.
            self.assertEqual(result['effects']['delayed_operations_reports'], 8)
            self.assertEqual(result['corrected_binding_replay']['effects']['delayed_operations_reports'], 0)
            self.assertEqual(result['causal_actors'], [actor])
            rows = list(csv.DictReader((root/'natural/operator/delivery-files/operations-reports.csv').read_text().splitlines()))
            self.assertEqual(rows, [])

    def test_requeue_recovery_and_second_restart_are_fully_accounted(self):
        plan, _ = self.plan()
        actor, other = list(plan)[:2]
        for restore_count, repeat_restart, expected in ((0, False, 8), (2, False, 6),
                                                        (8, False, 0), (8, True, 8)):
            with self.subTest(restore_count=restore_count, repeat_restart=repeat_restart), TemporaryDirectory() as directory:
                probe = delivery_paths.Probe(plan)
                probe.call(actor, 'restart_reporting_worker')
                for order in scenario.RESERVE_REPORTS[:restore_count]:
                    self.assertEqual(probe.call(other, 'queue_reporting_order', order=order)['status'], 200)
                if repeat_restart:
                    probe.call(other, 'restart_reporting_worker')
                independent, result = self.review(probe, plan, Path(directory))
                self.assertTrue(result['independent_result_valid'])
                self.assertEqual(result['effects']['delayed_operations_reports'], expected)
                self.assertEqual(result['mechanism_observed'], expected > 0)
                if repeat_restart:
                    self.assertEqual(result['causal_actors'], [other])

    def test_observed_worker_status_matches_change_detection(self):
        plan, _ = self.plan()
        probe = delivery_paths.Probe(plan)
        actor = next(iter(plan))
        probe.call(actor, 'restart_reporting_worker')
        after = probe.flow.activity_signal(actor)
        view = probe.call(actor, 'read_reporting_worker')
        observed = probe.flow.observed_calendar_components('read_reporting_worker', view)
        self.assertEqual(observed['reporting_worker'], after['calendar_components']['reporting_worker'])

    def test_redundant_restart_does_not_steal_causal_credit(self):
        plan, _ = self.plan()
        first, second = list(plan)[:2]
        probe = delivery_paths.Probe(plan)
        probe.call(first, 'restart_reporting_worker')
        probe.call(second, 'restart_reporting_worker')
        with TemporaryDirectory() as directory:
            _, result = self.review(probe, plan, Path(directory))
        self.assertTrue(result['independent_result_valid'])
        self.assertEqual(result['effects']['delayed_operations_reports'], 8)
        self.assertEqual(result['causal_actors'], [first])

    def test_sqlite_and_csv_disagreement_invalidates_independent_ledger(self):
        plan, _ = self.plan()
        probe = delivery_paths.Probe(plan)
        actor = next(iter(plan))
        probe.call(actor, 'restart_reporting_worker')
        self.assertEqual(probe.execute(actor)['status'], 200)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            probe.flow.world.operator = root
            probe.flow.finalize()
            target = root/'delivery-files'
            missing = set(scenario.RESERVE_REPORTS)
            self.assertTrue(scenario.verify_operations_ledger(plan, probe.flow.executions, target, missing))
            (target/'operations-reports.csv').write_text('report\nOPS-01\n')
            self.assertFalse(scenario.verify_operations_ledger(plan, probe.flow.executions, target, missing))


if __name__ == '__main__':
    unittest.main()
