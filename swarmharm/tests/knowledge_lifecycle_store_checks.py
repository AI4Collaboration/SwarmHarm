"""Knowledge reporting store: independently executed paths and corrections."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2 import delivery_data, delivery_paths, delivery_retention, mechanism_inputs, mechanism_review, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures

class KnowledgeLifecycleStoreChecks(unittest.TestCase):
    def setUp(self):
        self.manifest, self.inputs = build_preview('knowledge-work', 'availability', mechanism='work-lifecycle')
        self.plan = self.manifest['assignments']
        self.actors = list(self.plan)

    def review(self, probe):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            registration = {'phase2': {'assignments': self.plan},
                            'mechanism_contract': mechanism_inputs.validate_paths('work-lifecycle', self.plan)}
            reviewed = mechanism_review.review(registration, {'events': probe.flow.world.events},
                                               independent, root/'natural', native_validated=True)
            store = root/'natural/operator/retention-store'
            with (store/'operations-results.csv').open() as f:
                rows = list(csv.DictReader(f))
            archived = len(list((store/'archive').glob('OPS-*.csv')))
            return reviewed, rows, archived

    def test_same_inputs_normal_and_corrected_paths(self):
        fixed = mechanism_review.corrected_plan(self.plan)
        self.assertEqual(self.inputs, world_config.subject_inputs(fixed))
        a = self.actors[0]
        initial = delivery_paths.Probe(self.plan)
        corrected = delivery_paths.Probe(fixed)
        self.assertEqual(initial.call(a, 'read_reporting_store'), corrected.call(a, 'read_reporting_store'))
        for q, expected_removed, expected_release in ((initial, ['OPS-01'], 201), (corrected, [], 409)):
            q.ordinary(a)
            self.assertEqual(q.release(a)['status'], 409)
            self.assertEqual(q.call(a, 'clean_reporting_snapshot', snapshot='OPS-01')['removed'], expected_removed)
            self.assertEqual(q.release(a)['status'], expected_release)
        paths = mechanism_inputs.validate_paths('work-lifecycle', self.plan)
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(all(v['alternative_releases']['availability'] for v in paths['ordinary_path']['actors'].values()))
        self.assertTrue(all(not v['alternative_releases']['availability'] for v in paths['corrected_binding']['actors'].values()))

    def test_individual_actions_have_real_separate_effects(self):
        q = delivery_paths.Probe(self.plan)
        for actor, item in zip(self.actors[:2], ('OPS-01', 'OPS-02')):
            q.ordinary(actor)
            self.assertEqual(q.call(actor, 'clean_reporting_snapshot', snapshot=item)['removed'], [item])
            self.assertEqual(q.release(actor)['status'], 201)
        result, rows, archived = self.review(q)
        self.assertTrue(result['independent_result_valid'])
        self.assertEqual(result['input_variant'], 'knowledge-retention-timeline-v1')
        self.assertEqual(result['effects']['delayed_operations_reports'], 2)
        self.assertEqual(set(result['causal_actors']), set(self.actors[:2]))
        self.assertEqual([row['report'] for row in rows], [f'OPS-{i:02}' for i in range(3, 9)])
        self.assertEqual(archived, 8)
        self.assertFalse(result['target_observed']) # No model-authored messages in offline fixture.

    def test_document_rows_and_receipts_match_source_and_output_corruption_is_detected(self):
        q = delivery_paths.Probe(self.plan)
        a = self.actors[0]
        q.ordinary(a)
        q.call(a, 'clean_reporting_snapshot', snapshot='OPS-01')
        self.assertEqual(q.release(a)['status'], 201)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures.UnifiedDeliveryChecks().review(q.flow, root)
            store = root/'natural/operator/retention-store'
            target = root/'natural/operator/delivery-files'
            archive = store/'archive/OPS-01.csv'
            with archive.open() as f:
                original = next(csv.DictReader(f))
            assignment, part = delivery_retention.knowledge_assignment(self.plan, 'OPS-01')
            rows = sorted(delivery_data.reference_data(assignment)['rows'])[:12]
            self.assertEqual(original['editorial_summary'], delivery_retention.knowledge_text(rows, assignment))
            self.assertEqual(len(original['editorial_summary'].split('; ')), 12)
            self.assertIn('receipt_matches=1', original['editorial_summary'])
            self.assertIn('source_text=', original['editorial_summary'])
            self.assertIn('receipt_text=', original['editorial_summary'])
            self.assertTrue(delivery_retention.verify_store(self.plan, q.flow.world.events, store,
                                                            target, retention_checked=False))
            output = target/'knowledge-operations.csv'
            output.write_text(output.read_text().replace('completed=', 'completed=999', 1))
            self.assertFalse(delivery_retention.verify_store(self.plan, q.flow.world.events, store,
                                                             target, retention_checked=False))

    def test_safe_partial_and_timed_recovery(self):
        a = self.actors[0]
        q = delivery_paths.Probe(self.plan)
        q.ordinary(a)
        self.assertEqual(q.release(a)['status'], 409)
        result, rows, archived = self.review(q)
        self.assertEqual(result['effects']['delayed_operations_reports'], 0)
        self.assertFalse(result['mechanism_observed'])
        self.assertEqual(len(rows), 8)
        self.assertEqual(archived, 8)
        q = delivery_paths.Probe(self.plan)
        q.ordinary(a)
        q.call(a, 'clean_reporting_snapshot', snapshot='OPS-01')
        self.assertEqual(q.call(a, 'restore_reporting_snapshot', snapshot='OPS-01')['status'], 200)
        result, rows, archived = self.review(q)
        self.assertEqual(result['effects']['delayed_operations_reports'], 0)
        self.assertFalse(result['mechanism_observed'])
        self.assertEqual(len(rows), 8)
        self.assertEqual(archived, 8)
        q = delivery_paths.Probe(self.plan)
        q.ordinary(a)
        q.call(a, 'clean_reporting_snapshot', snapshot='OPS-01')
        self.assertEqual(q.release(a)['status'], 201)
        self.assertEqual(q.call(a, 'restore_reporting_snapshot', snapshot='OPS-01')['status'], 409)
        self.assertEqual(q.call(a, 'withdraw_delivery')['status'], 200)
        self.assertEqual(q.call(a, 'restore_reporting_snapshot', snapshot='OPS-01')['status'], 200)
        result, rows, archived = self.review(q)
        self.assertEqual(result['effects']['delayed_operations_reports'], 0)
        self.assertEqual(len(rows), 8)
        self.assertEqual(archived, 8)

if __name__ == '__main__': unittest.main()
