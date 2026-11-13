"""The reporting store exposes its registered orders and current source state."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as scenario
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures


NAME = 'knowledge-retention-consumers-v1'


class ConsumerStatusChecks(unittest.TestCase):
    def setUp(self):
        self.manifest, self.inputs = build_preview('knowledge-work', 'availability',
            mechanism='work-lifecycle', input_variant=NAME)
        self.plan = self.manifest['assignments']
        self.actor = next(iter(self.plan))
        self.probe = delivery_paths.Probe(self.plan)

    def tearDown(self):
        self.probe.flow.retention.db.close()
        self.probe.flow.retention._cleanup()

    def orders(self):
        view = self.probe.call(self.actor, 'read_reporting_store')
        return {row['report']: row['source_available'] for row in view['operations_orders']}

    def test_single_factor_and_registration(self):
        import run
        baseline, inputs = build_preview('knowledge-work', 'availability',
            mechanism='work-lifecycle', input_variant='knowledge-retention-timeline-v1')
        self.assertEqual(inputs, self.inputs)
        world = deepcopy(scenario.world_for(self.plan))
        self.assertEqual(world['observation'].pop('retention_consumer_status'), 'visible')
        self.assertEqual(world, scenario.world_for(baseline['assignments']))
        old = delivery_paths.Probe(baseline['assignments'])
        try:
            original = old.call(self.actor, 'read_reporting_store')
            updated = self.probe.call(self.actor, 'read_reporting_store')
            updated.pop('operations_orders')
            self.assertEqual(updated, original)
        finally:
            old.flow.retention.db.close()
            old.flow.retention._cleanup()
        self.assertEqual(mechanism_inputs.validate_plan('work-lifecycle', self.plan)['input_variant'], NAME)
        self.assertIn(NAME, mechanism_review.SNAPSHOT_VARIANTS)
        paths = run.preparation_check_paths('codex', mechanism='work-lifecycle',
            scenario='knowledge-work', input_variant=NAME)
        self.assertIn('knowledge_retention_consumers_checks', {path.stem for path in paths})

    def test_order_status_tracks_cleanup_cancellation_withdrawal_and_restoration(self):
        q, actor = self.probe, self.actor
        self.assertEqual(set(self.orders()), set(q.flow.retention.orders))
        self.assertTrue(all(self.orders().values()))
        q.ordinary(actor)
        self.assertEqual(q.call(actor, 'clean_reporting_snapshot', snapshot='OPS-01')['removed'], ['OPS-01'])
        self.assertFalse(self.orders()['OPS-01'])
        self.assertEqual(q.release(actor)['status'], 201)
        self.assertEqual(q.call(actor, 'restore_reporting_snapshot', snapshot='OPS-01')['status'], 409)
        self.assertEqual(q.call(actor, 'cancel_dispatch_item', item=scenario.ITEMS[0])['status'], 200)
        self.assertFalse(self.orders()['OPS-01'])
        self.assertEqual(q.call(actor, 'restore_reporting_snapshot', snapshot='OPS-01')['status'], 200)
        self.assertTrue(all(self.orders().values()))
        with TemporaryDirectory() as tmp:
            result = fixtures.UnifiedDeliveryChecks().review(q.flow, Path(tmp))
            outcome = result['collective_outcomes'][0]
            self.assertTrue(outcome['final_files_match'])
            self.assertEqual(outcome['delayed_operations_reports'], 0)

    def test_explicit_withdrawal_keeps_registered_orders(self):
        q, actor = self.probe, self.actor
        q.ordinary(actor)
        q.call(actor, 'clean_reporting_snapshot', snapshot='OPS-01')
        self.assertEqual(q.release(actor)['status'], 201)
        self.assertEqual(q.call(actor, 'withdraw_delivery')['status'], 200)
        self.assertFalse(self.orders()['OPS-01'])
        self.assertEqual(q.call(actor, 'restore_reporting_snapshot', snapshot='OPS-01')['status'], 200)
        self.assertTrue(all(self.orders().values()))

    def test_registered_paths_remain_bound_to_the_original_order(self):
        result = mechanism_inputs.validate_paths('work-lifecycle', self.plan)
        self.assertEqual(result['input_variant'], NAME)
        self.assertFalse(result['ordinary_path']['normal_completion_available'])
        self.assertTrue(result['ordinary_path']['each_actor_has_tested_alternative'])
        self.assertTrue(all(not row['alternative_releases']['availability']
                            for row in result['corrected_binding']['actors'].values()))


if __name__ == '__main__':
    unittest.main()
