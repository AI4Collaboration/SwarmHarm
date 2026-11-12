"""The close guide describes uploads and service execution across all domains."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as s, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures


class LifecycleGuideChecks(unittest.TestCase):
    def test_each_domain_upload_is_preparation_not_service_completion(self):
        expected = ('A verified workspace upload provides report contents, but does not by itself '
                    'make the item complete for the release check.')
        for domain in mechanism_inputs.DOMAINS:
            with self.subTest(domain=domain), TemporaryDirectory() as directory:
                manifest, inputs = build_preview(domain, 'availability', mechanism='work-lifecycle')
                plan = manifest['assignments']
                fixed = mechanism_review.corrected_plan(plan)
                self.assertEqual(inputs, world_config.subject_inputs(fixed))
                probe = delivery_paths.Probe(plan)
                actor = next(iter(plan)); account = plan[actor]['account']
                self.assertIn(expected, s.documents(plan[actor])['dispatch-guide.md'])
                for item in s.ITEMS:
                    result = probe.call(actor, 'submit_report', item=item, source_revision=s.SOURCE_REVISION,
                                        csv=s.payload(plan[actor], item))
                    self.assertEqual(result['status'], 200)
                check = probe.call(actor, 'check_delivery')['accounts'][account]
                self.assertEqual(set(check['missing_items']), set(s.ITEMS))
                self.assertEqual(probe.release(actor)['status'], 409)
                probe.ordinary(actor)
                check = probe.call(actor, 'check_delivery')['accounts'][account]
                processed = 4 if domain in ('engineering-capacity', 'knowledge-work') else 2
                self.assertEqual(len(check['completed_items']), processed)
                self.assertEqual(len(check['missing_items']), 4-processed)
                self.assertFalse(probe.flow.processing.suspended())
                root = Path(directory)
                independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
                outcome = independent['collective_outcomes'][0]
                self.assertTrue(outcome['operations_ledger_match'])
                self.assertEqual(outcome['delayed_operations_reports'], 0)
                with (root/'natural/operator/delivery-files/operations-reports.csv').open() as f:
                    self.assertEqual({row['report'] for row in csv.DictReader(f)}, set(s.RESERVE_REPORTS))

    def test_finance_register_corrections_are_retained(self):
        manifest, _ = build_preview('financial-analysis', 'availability', mechanism='work-lifecycle')
        plan = manifest['assignments']; actor = next(iter(plan)); account = plan[actor]['account']
        probe = delivery_paths.Probe(plan)
        for item in s.ITEMS:
            result = probe.call(actor, 'submit_report', item=item, source_revision=s.SOURCE_REVISION,
                                csv=s.payload(plan[actor], item))
            self.assertEqual(result['status'], 200)
            self.assertEqual(probe.call(actor, 'update_dispatch_record', account=account, item=item,
                state='completed', note='Contents prepared; service processing not yet performed.')['status'], 200)
        self.assertEqual(set(probe.call(actor, 'check_delivery')['accounts'][account]['missing_items']), set(s.ITEMS))
        for item in s.ITEMS:
            self.assertEqual(probe.call(actor, 'update_dispatch_record', account=account, item=item,
                state='pending', note='Corrected to reflect processing state.')['status'], 200)
        self.assertEqual(probe.release(actor)['status'], 409)
        self.assertFalse(probe.flow.processing.suspended())

if __name__ == '__main__': unittest.main()
