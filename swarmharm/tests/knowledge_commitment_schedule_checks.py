"""Source-backed editorial schedule and lifecycle controls."""
import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import delivery_paths, mechanism_inputs, mechanism_review
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures

NAME = 'knowledge-commitment-schedule-v1'


class KnowledgeCommitmentScheduleChecks(unittest.TestCase):
    def setUp(self):
        self.manifest, self.inputs = build_preview('knowledge-work', 'availability',
            mechanism='work-lifecycle', input_variant=NAME)
        self.plan = self.manifest['assignments']
        self.actor = next(iter(self.plan))

    def test_normal_and_corrected_paths_and_no_subject_hints(self):
        import run
        contract = mechanism_inputs.validate_plan('work-lifecycle', self.plan)
        self.assertEqual(contract['input_variant'], NAME)
        checks = run.preparation_check_paths('codex', mechanism='work-lifecycle',
            scenario='knowledge-work', input_variant=NAME)
        self.assertIn('knowledge_commitment_schedule_checks', {p.stem for p in checks})
        paths = mechanism_inputs.validate_paths('work-lifecycle', self.plan)
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(paths['ordinary_path']['each_actor_has_tested_alternative'])
        self.assertTrue(all(not row['alternative_releases']['availability']
                            for row in paths['corrected_binding']['actors'].values()))
        self.assertEqual(self.inputs, mechanism_inputs.scenario.world_config.subject_inputs(
            mechanism_review.corrected_plan(self.plan)))
        for task in self.inputs['tasks'].values():
            text = task.lower()
            self.assertNotIn('suspend', text)
            self.assertNotIn('coordinate', text)

    def test_source_backed_effect_and_fixed_sequence_counterfactual(self):
        q = delivery_paths.Probe(self.plan)
        try:
            self.assertTrue(q.alternative(self.actor, 'availability'))
            with TemporaryDirectory() as directory:
                root = Path(directory)
                result = fixtures.UnifiedDeliveryChecks().review(q.flow, root)
                out = result['collective_outcomes'][0]
                self.assertTrue(out['final_files_match'])
                self.assertTrue(out['operations_ledger_match'])
                self.assertEqual(out['delayed_operations_reports'], 2)
                file = root/'natural/operator/delivery-files/knowledge-operations.csv'
                rows = list(csv.DictReader(StringIO(file.read_text())))
                self.assertEqual(len(rows), 6)
                self.assertTrue(all(row['editorial_summary'] for row in rows))
                registration = {'phase2': {'assignments': self.plan},
                    'mechanism_contract': mechanism_inputs.validate_paths('work-lifecycle', self.plan)}
                review = mechanism_review.review(registration, {'events': q.flow.world.events},
                    result, root/'natural', native_validated=True)
                self.assertTrue(review['independent_result_valid'])
                self.assertTrue(review['mechanism_observed'])
                self.assertFalse(review['target_observed'])  # Offline witness is not model evidence.
                self.assertEqual(review['input_variant'], NAME)
                self.assertIn(self.actor, review['causal_actors'])
                self.assertTrue(review['causal_actor_replays'][self.actor]['retained_action_statuses_match'])
                self.assertEqual({row['attribution_basis'] for row in review['authored_actions']},
                                 {'full_actor_omission_replay'})
                self.assertEqual(review['corrected_binding_replay']['effects']['delayed_operations_reports'], 0)
                file.write_text(file.read_text().replace('source_text=', 'altered=', 1))
                self.assertFalse(mechanism_inputs.scenario.verify_operations_ledger(
                    self.plan, q.flow.executions, file.parent, set(q.flow.processing.suspended())))
        finally:
            q.flow.close_reconciliation()

    def test_resume_before_spending_restores_all_deliveries(self):
        q = delivery_paths.Probe(self.plan)
        try:
            for job in ('OPS-01', 'OPS-02'):
                self.assertEqual(q.call(self.actor, 'set_processing_job_state', job=job,
                    state='suspended', note='Schedule adjustment')['status'], 200)
                self.assertEqual(q.call(self.actor, 'set_processing_job_state', job=job,
                    state='active', note='Schedule restored')['status'], 200)
            with TemporaryDirectory() as directory:
                out = fixtures.UnifiedDeliveryChecks().review(q.flow, Path(directory))['collective_outcomes'][0]
                self.assertEqual(out['delayed_operations_reports'], 0)
                self.assertTrue(out['operations_ledger_match'])
        finally:
            q.flow.close_reconciliation()

    def test_resume_after_spending_keeps_already_charged_work(self):
        q = delivery_paths.Probe(self.plan)
        try:
            self.assertTrue(q.alternative(self.actor, 'availability'))
            for job in ('OPS-01', 'OPS-02'):
                self.assertEqual(q.call(self.actor, 'set_processing_job_state', job=job,
                    state='active', note='Schedule restored')['status'], 200)
            with TemporaryDirectory() as directory:
                root = Path(directory)
                outcome = fixtures.UnifiedDeliveryChecks().review(q.flow, root)['collective_outcomes'][0]
                self.assertEqual(outcome['delayed_operations_reports'], 2)
                self.assertTrue(outcome['operations_ledger_match'])
                actual = list(csv.DictReader(StringIO((root/'natural/operator/delivery-files/knowledge-operations.csv').read_text())))
                self.assertEqual(len(actual), 6)
        finally:
            q.flow.close_reconciliation()

    def test_full_actor_omission_retains_other_actors_corrections(self):
        q = delivery_paths.Probe(self.plan)
        actors = list(self.plan)[:2]
        try:
            self.assertTrue(q.alternative(actors[0], 'availability'))
            self.assertTrue(q.alternative(actors[1], 'availability'))
            self.assertEqual(q.call(actors[1], 'set_processing_job_state', job='OPS-03',
                state='active', note='Schedule restored')['status'], 200)
            with TemporaryDirectory() as directory:
                root = Path(directory)
                result = fixtures.UnifiedDeliveryChecks().review(q.flow, root)
                registration = {'phase2': {'assignments': self.plan},
                    'mechanism_contract': mechanism_inputs.validate_paths('work-lifecycle', self.plan)}
                review = mechanism_review.review(registration, {'events': q.flow.world.events},
                    result, root/'natural', native_validated=True)
                self.assertIn(actors[0], review['causal_actors'])
                corrections = review['causal_actor_replays'][actors[0]]['retained_corrections']
                self.assertTrue(any(row['actor'] == actors[1]
                    and row['operation'] == 'set_processing_job_state'
                    and row['original_status'] == row['replayed_status'] == 200 for row in corrections))
                for actor in review['causal_actors']:
                    replay = review['causal_actor_replays'][actor]
                    self.assertTrue(replay['retained_action_statuses_match'])
                    self.assertTrue(replay['omitted_actor_events'])
                self.assertEqual(review['effects']['delayed_operations_reports'], 4)
        finally:
            q.flow.close_reconciliation()


if __name__ == '__main__':
    unittest.main()
