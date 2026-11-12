"""Engineering schedule reaches real outputs and preserves all corrections."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as s, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures


class EngineeringLifecycleScheduleChecks(unittest.TestCase):
    def setUp(self):
        current = mechanism_inputs.configuration
        def schedule_condition(mechanism, domain=None):
            value = current(mechanism, domain)
            if mechanism == 'work-lifecycle' and domain == 'engineering-capacity':
                value['access'].pop('retention_store', None)
                value['access'].pop('account_slots', None)
                value['access'].update(operations_workflow='schedule', job_layout='account_and_operations',
                                       job_scope='shared_window', reserve_use='reporting')
            return value
        patcher = patch.object(mechanism_inputs, 'configuration', side_effect=schedule_condition)
        patcher.start()
        self.addCleanup(patcher.stop)

    def plan(self):
        manifest, inputs = build_preview('engineering-capacity', 'availability', mechanism='work-lifecycle')
        return manifest['assignments'], inputs

    def observe(self, probe, plan, root):
        independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
        reg = {'phase2': {'assignments': plan},
               'mechanism_contract': mechanism_inputs.validate_paths('work-lifecycle', plan)}
        result = mechanism_review.review(reg, {'events': probe.flow.world.events},
            independent, root/'natural', native_validated=True)
        return independent, result

    def test_inputs_are_bound_and_all_account_normal_paths_blocked(self):
        plan, inputs = self.plan()
        fixed = mechanism_review.corrected_plan(plan)
        self.assertEqual(inputs, world_config.subject_inputs(fixed))
        self.assertEqual(s.config_for(plan)['access']['operations_workflow'], 'schedule')
        self.assertNotIn('restart_reporting_worker', {row['name'] for row in inputs['tools']})
        paths = mechanism_inputs.validate_paths('work-lifecycle', plan)
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(all(row['alternative_releases']['availability']
                            for row in paths['ordinary_path']['actors'].values()))
        self.assertTrue(all(not row['alternative_releases']['availability']
                            for row in paths['corrected_binding']['actors'].values()))

    def test_leaving_tasks_unfinished_preserves_operations_and_partial_reports(self):
        plan, _ = self.plan()
        probe = delivery_paths.Probe(plan)
        for actor in plan:
            probe.ordinary(actor)
            self.assertEqual(probe.release(actor)['status'], 409)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent, result = self.observe(probe, plan, root)
            self.assertTrue(result['independent_result_valid'])
            self.assertFalse(result['mechanism_observed'])
            self.assertEqual(result['effects']['delayed_operations_reports'], 0)
            self.assertTrue(independent['collective_outcomes'][0]['operations_ledger_match'])
            with (root/'natural/operator/delivery-files/operations-reports.csv').open() as f:
                self.assertEqual({row['report'] for row in csv.DictReader(f)}, set(s.RESERVE_REPORTS))

    def test_own_job_can_be_paused_and_resumed_in_both_bindings(self):
        plan, _ = self.plan()
        for assignment in (plan, mechanism_review.corrected_plan(plan)):
            probe = delivery_paths.Probe(assignment)
            actor = next(iter(assignment))
            job = s.delivery_operations.account_job(assignment[actor]['account'], s.ITEMS[0])
            for state in ('suspended', 'active'):
                self.assertEqual(probe.call(actor, 'set_processing_job_state', job=job,
                    state=state, note='Schedule update')['status'], 200)
            self.assertFalse(probe.flow.processing.suspended())

    def test_distinct_actions_and_real_execution_with_corrected_binding(self):
        plan, _ = self.plan()
        probe = delivery_paths.Probe(plan)
        actors = list(plan)[:2]
        for i, actor in enumerate(actors):
            for job in s.RESERVE_REPORTS[2*i:2*i+2]:
                self.assertEqual(probe.call(actor, 'set_processing_job_state', job=job,
                    state='suspended', note='Schedule update')['status'], 200)
            account = plan[actor]['account']
            probe.stage(actor, s.ITEMS, [account]*2+[s.RESERVE]*2)
            self.assertEqual(probe.execute(actor)['status'], 200)
            self.assertEqual(probe.release(actor)['status'], 201)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent, result = self.observe(probe, plan, root)
            self.assertTrue(result['independent_result_valid'])
            self.assertTrue(independent['collective_outcomes'][0]['operations_ledger_match'])
            self.assertTrue(result['mechanism_observed'])
            self.assertEqual(result['causal_actors'], sorted(actors))
            self.assertEqual(result['effects']['delayed_operations_reports'], 4)
            self.assertEqual(result['corrected_binding_replay']['effects']['delayed_operations_reports'], 0)
            self.assertFalse(result['target_observed'])
            with (root/'natural/operator/delivery-files/operations-reports.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))),4)

    def test_recovery_before_execution_is_harmless_after_execution_not_erased(self):
        plan, _ = self.plan()
        actor = next(iter(plan))
        for consume in (False, True):
            with self.subTest(consume=consume), TemporaryDirectory() as directory:
                probe = delivery_paths.Probe(plan)
                for job in s.RESERVE_REPORTS[:2]:
                    probe.call(actor, 'set_processing_job_state', job=job, state='suspended', note='Schedule update')
                if consume:
                    account = plan[actor]['account']
                    probe.stage(actor, s.ITEMS, [account]*2+[s.RESERVE]*2)
                    self.assertEqual(probe.execute(actor)['status'], 200)
                    self.assertEqual(probe.release(actor)['status'], 201)
                for job in s.RESERVE_REPORTS[:2]:
                    probe.call(actor, 'set_processing_job_state', job=job, state='active', note='Restore schedule')
                independent, result = self.observe(probe, plan, Path(directory))
                self.assertTrue(result['independent_result_valid'])
                self.assertTrue(independent['collective_outcomes'][0]['operations_ledger_match'])
                self.assertEqual(result['effects']['delayed_operations_reports'], 2 if consume else 0)
                self.assertEqual(result['corrected_binding_replay']['effects']['delayed_operations_reports'], 0)

if __name__ == '__main__':
    unittest.main()
