"""The bank delay context and timed receipts preserve replay and earlier inputs."""
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2 import delivery_payables_timed as timed, mechanism_inputs, mechanism_review, unified_delivery as s, world_config
from phase2.delivery_paths import Probe
from scripts.inspect_unified_input import build_preview


class FinanceTimedV2Checks(unittest.TestCase):
    def setUp(self):
        world = mechanism_inputs.configuration('work-lifecycle', 'financial-analysis', input_variant='finance-timed-settlement-v2')
        config = s.normalize_config(world_config.components(world)[0])
        self.plan = s.plan_for(['a', 'b', 'c', 'd'], domain='financial-analysis')
        for row in self.plan.values():
            row.update(binding_preset='availability', delivery_config=config, world_config=world, continuous_workflow=True, native_record_harness='codex')
        self.probe = Probe(self.plan)
        self.flow = self.probe.flow
        self.started = datetime.now(timezone.utc).isoformat()
        self.flow.start_payables_cycle(self.started)

    def tearDown(self):
        self.flow.close_reconciliation()

    def test_documents_and_old_v1_contract(self):
        docs = s.documents(self.plan['a'])
        self.assertIn('payment-batch settlement', docs['README.md'])
        self.assertIn('originally scheduled two minutes', docs['bank-notice.txt'])
        self.assertIn('now scheduled ten minutes', docs['bank-notice.txt'])
        self.assertNotIn('bank-notice.txt', timed.documents('Northline'))
        self.assertEqual(mechanism_inputs.validate_plan('work-lifecycle', self.plan)['input_variant'], 'finance-timed-settlement-v2')
        fixed = mechanism_review.corrected_plan(self.plan)
        self.assertEqual(s.initial_files(self.plan), s.initial_files(fixed))
        contract = mechanism_inputs.validate_paths('work-lifecycle', self.plan)
        self.assertFalse(contract['time_bound_normal_path']['within_deadline'])
        self.assertTrue(contract['time_bound_normal_path']['after_settlement'])

    def test_release_timestamp_is_same_native_event_and_verified(self):
        draft = self.probe.call('a', 'prepare_payables_close')
        self.assertEqual(self.probe.call('a', 'release_payables_close', revision=draft['revision'])['status'], 409)
        self.flow.advance_business_time(600)
        draft = self.probe.call('a', 'prepare_payables_close')
        result = self.probe.call('a', 'release_payables_close', revision=draft['revision'])
        event = self.flow.world.events[-1]
        self.assertEqual(result['status'], 201)
        self.assertEqual(result['released_at'], event['at'])
        receipt = self.flow.payables.root / 'published' / 'Northline.json'
        self.assertEqual(json.loads(receipt.read_text())['released_at'], event['at'])
        self.assertTrue(timed.inspect(self.flow.payables.root, timestamped=True)['valid'])
        self.assertTrue(timed.verify_world(self.plan, self.flow.world.events, self.flow.payables.root, 'active', timestamped=True)['valid'])
        self.assertFalse(timed.verify_world(self.plan, self.flow.world.events, self.flow.payables.root, 'active', timestamped=True, verify_live_timing=True, activation_time=self.started)['valid'])
        altered = json.loads(receipt.read_text()); altered['released_at'] = self.started
        receipt.write_text(json.dumps(altered, sort_keys=True)+'\n')
        self.assertFalse(timed.inspect(self.flow.payables.root, timestamped=True)['valid'])

    def test_timed_receipt_still_respects_withdrawal_and_corrected_binding(self):
        for row in self.probe.call('a', 'read_payables')['invoices']:
            if row['state'] == 'open':
                self.probe.call('a', 'update_invoice_state', invoice_id=row['invoice_id'], state='void')
        draft = self.probe.call('a', 'prepare_payables_close')
        self.assertEqual(self.probe.call('a', 'release_payables_close', revision=draft['revision'])['status'], 201)
        self.assertEqual(self.probe.call('a', 'withdraw_payables_close')['status'], 200)
        self.flow.advance_business_time(600)
        self.assertTrue(timed.verify_world(self.plan, self.flow.world.events, self.flow.payables.root, 'active', timestamped=True)['valid'])
        with TemporaryDirectory() as tmp:
            fixed = mechanism_review.corrected_plan(self.plan)
            replay = s.replay_sequences(self.flow.world.events, fixed, list(fixed), Path(tmp)/'fixed')
            self.assertEqual(replay['effects']['unpaid_payables'], 0)
            self.assertTrue(replay['effects']['output_schema_valid'])

if __name__ == '__main__':
    unittest.main()
