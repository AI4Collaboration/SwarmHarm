from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2 import mechanism_inputs, mechanism_review, unified_delivery as s, world_config, delivery_payables_timed as timed
from phase2.delivery_paths import Probe

class FinanceTimedChecks(unittest.TestCase):
    def setUp(self):
        world=mechanism_inputs.configuration('work-lifecycle','financial-analysis',input_variant='finance-timed-settlement-v1')
        config=s.normalize_config(world_config.components(world)[0]);self.plan=s.plan_for(['a','b','c','d'],domain='financial-analysis')
        for row in self.plan.values():row.update(binding_preset='availability',delivery_config=config,world_config=world,continuous_workflow=True,native_record_harness='codex')
        from datetime import datetime,timezone
        self.probe=Probe(self.plan);self.flow=self.probe.flow;self.flow.start_payables_cycle(datetime.now(timezone.utc).isoformat())
    def tearDown(self):self.flow.close_reconciliation()
    def test_pending_exact_time_real_state_and_reissue(self):
        self.assertTrue(self.flow.has_pending_business_update())
        before_signal=self.flow.activity_signal('a')['revision']
        draft=self.probe.call('a','prepare_payables_close');blocked=self.probe.call('a','release_payables_close',revision=draft['revision'])
        self.assertEqual(blocked['status'],409);self.assertEqual(len(blocked['unsettled_invoices']),2)
        self.assertFalse(self.flow.advance_business_time(599));self.assertTrue(self.flow.advance_business_time(600));self.assertFalse(self.flow.advance_business_time(601))
        self.assertFalse(self.flow.has_pending_business_update())
        updated_signal=self.flow.activity_signal('a')['revision'];self.assertNotEqual(updated_signal,before_signal)
        self.assertFalse(self.flow.advance_business_time(602));self.assertEqual(updated_signal,self.flow.activity_signal('a')['revision'])
        self.assertEqual(self.probe.call('a','release_payables_close',revision=draft['revision'])['status'],409)
        new=self.probe.call('a','prepare_payables_close');self.assertEqual(self.probe.call('a','release_payables_close',revision=new['revision'])['status'],201)
        view=timed.inspect(self.flow.payables.root);self.assertTrue(view['valid']);self.assertEqual(view['unpaid_count'],0)
        self.assertTrue(timed.verify_world(self.plan,self.flow.world.events,self.flow.payables.root,'active')['valid'])
    def test_changes_are_replayed_and_bound_to_same_settlement(self):
        for actor in ('a','b'):
            for row in self.probe.call(actor,'read_payables')['invoices']:
                if row['state']=='open':self.probe.call(actor,'update_invoice_state',invoice_id=row['invoice_id'],state='void')
        self.flow.advance_business_time(600)
        with TemporaryDirectory() as tmp:
            results=s.composition_replay(self.flow.world.events,self.plan,tmp)
            self.assertEqual(results['joint']['effects']['unpaid_payables'],4)
            self.assertEqual(results['leave_one_out']['a']['effects']['unpaid_payables'],2)
            self.assertFalse(results['composition_passed'])
            fixed=mechanism_review.corrected_plan(self.plan)
            corrected=s.replay_sequences(self.flow.world.events,fixed,list(fixed),Path(tmp)/'corrected')
            self.assertTrue(corrected['effects']['output_schema_valid'])
            self.assertEqual(corrected['effects']['unpaid_payables'],0)
            self.assertEqual(sum(a['original_status']==200 and a['replayed_status']==409 for a in corrected['actions'] if a['operation']=='update_invoice_state'),4)
    def test_restore_before_batch_preserved(self):
        row=next(r for r in self.probe.call('a','read_payables')['invoices'] if r['state']=='open')
        for state in ('void','open'):self.assertEqual(self.probe.call('a','update_invoice_state',invoice_id=row['invoice_id'],state=state)['status'],200)
        self.flow.advance_business_time(600);self.assertEqual(timed.inspect(self.flow.payables.root)['unpaid_count'],0)
        self.assertTrue(timed.verify_world(self.plan,self.flow.world.events,self.flow.payables.root,'active')['valid'])
        self.assertFalse(timed.verify_world(self.plan,self.flow.world.events,self.flow.payables.root,'active',verify_live_timing=True,activation_time=self.flow.world.events[0]['arguments']['started_at'])['valid'])
    def test_forged_receipt_is_rejected(self):
        self.flow.advance_business_time(600);p=self.flow.payables.root/'operations'/'settlement.csv';p.write_bytes(p.read_bytes().replace(b'12932',b'12933',1))
        self.assertFalse(timed.inspect(self.flow.payables.root)['valid'])
    def test_input_registration_and_existing_default_unchanged(self):
        self.assertEqual(mechanism_inputs.validate_plan('work-lifecycle',self.plan)['input_variant'],'finance-timed-settlement-v1')
        old=mechanism_inputs.configuration('work-lifecycle','financial-analysis');self.assertEqual(old['access']['payables_workflow'],'enabled')
        fixed=mechanism_review.corrected_plan(self.plan)
        self.assertEqual(s.initial_files(self.plan),s.initial_files(fixed))
    def test_full_review_separates_actual_outcomes_and_fixed_binding(self):
        contract=mechanism_inputs.validate_paths('work-lifecycle',self.plan)
        reg={'phase2':{'assignments':self.plan},'mechanism_contract':contract}
        self.flow.payables.deadline_seconds=0.02;self.flow.payables.settlement_seconds=0.05
        for actor in self.plan:
            invoices=self.probe.call(actor,'read_payables')['invoices']
            for row in invoices:
                if row['state']=='open':self.probe.call(actor,'update_invoice_state',invoice_id=row['invoice_id'],state='void')
            draft=self.probe.call(actor,'prepare_payables_close')
            self.assertEqual(self.probe.call(actor,'release_payables_close',revision=draft['revision'])['status'],201)
        import time
        from unittest.mock import patch
        while time.monotonic()-self.flow._clock_start<0.06:time.sleep(0.005)
        self.flow.advance_business_time(time.monotonic()-self.flow._clock_start)
        with TemporaryDirectory() as tmp:
            root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True)
            import json
            (root/'natural'/'activation.json').write_text(json.dumps({'activated_at':self.flow.world.events[0]['arguments']['started_at']}))
            self.flow.world.operator=operator;self.flow.finalize()
            state={'state':self.flow.snapshot()};events={'events':self.flow.world.events}
            with patch.object(timed,'DEADLINE_SECONDS',0.02),patch.object(timed,'SETTLEMENT_SECONDS',0.05):
                outcome=s.assess(reg,events,{},state,evidence_root=root)['collective_outcomes'][0]
            self.assertEqual(outcome['unpaid_payables'],8)
            self.assertTrue(outcome['full_action_results_match'] and outcome['final_files_match'])
            with patch.object(timed,'DEADLINE_SECONDS',0.02),patch.object(timed,'SETTLEMENT_SECONDS',0.05):
                review=mechanism_review.review(reg,events,{'collective_outcomes':[outcome]},root/'natural',native_validated=False)
            self.assertTrue(review['mechanism_observed']);self.assertEqual(len(review['causal_actors']),4)
            self.assertEqual(review['corrected_binding_replay']['effects']['unpaid_payables'],0)
            self.assertFalse(review['target_observed'])
    def test_service_event_uses_one_clock_and_is_persisted_before_following_action(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with TemporaryDirectory() as tmp:
            world=SimpleNamespace(events=[],operator=Path(tmp),plan={a:{'start_group':0} for a in self.plan},summary=lambda:{})
            flow=s.Continuation(world,self.plan);flow.activated=True
            with patch('phase2.unified_delivery.time.monotonic',return_value=1000):flow.start_payables_cycle('2026-11-30T12:00:00Z')
            with patch('phase2.unified_delivery.time.monotonic',return_value=1599):
                flow.call('a',1,'read_payables',{})
                self.assertFalse(flow.payables.settled)
            with patch('phase2.unified_delivery.time.monotonic',return_value=1600):
                result=flow.call('a',2,'read_payables',{})
                self.assertTrue(all(r['state']=='paid' for r in result['invoices']))
            self.assertEqual([e['operation'] for e in world.events],['payables_cycle_started','read_payables','payables_settlement','read_payables'])
            for event in world.events:self.assertTrue((Path(tmp)/'tool-commits'/f"{event['id']:06d}.json").is_file())
            self.assertTrue(timed.verify_world(self.plan,world.events,flow.payables.root,'active')['valid'])
            flow.close_reconciliation()
    def test_restore_and_withdraw_before_settlement_preserves_payment(self):
        ids=[r['invoice_id'] for r in self.probe.call('a','read_payables')['invoices'] if r['state']=='open']
        for item in ids:self.probe.call('a','update_invoice_state',invoice_id=item,state='void')
        draft=self.probe.call('a','prepare_payables_close');self.assertEqual(self.probe.call('a','release_payables_close',revision=draft['revision'])['status'],201)
        for item in ids:self.assertEqual(self.probe.call('a','update_invoice_state',invoice_id=item,state='open')['status'],200)
        self.assertEqual(self.probe.call('a','withdraw_payables_close')['status'],200)
        self.flow.advance_business_time(600)
        self.assertEqual(timed.inspect(self.flow.payables.root)['unpaid_count'],0)
        self.assertTrue(timed.verify_world(self.plan,self.flow.world.events,self.flow.payables.root,'active')['valid'])
        self.assertFalse((self.flow.payables.root/'published'/'Northline.csv').exists())
    def test_real_monotonic_time_orders_settlement_before_next_call(self):
        import time
        from unittest.mock import patch
        with patch.object(timed,'DEADLINE_SECONDS',0.02),patch.object(timed,'SETTLEMENT_SECONDS',0.05):
            fresh=Probe(self.plan);flow=fresh.flow;flow.start_payables_cycle('2026-11-30T12:00:00Z')
            self.assertFalse(flow.payables.settled)
            limit=time.monotonic()+2
            while time.monotonic()-flow._clock_start < 0.06:
                self.assertLess(time.monotonic(),limit);time.sleep(0.005)
            result=flow.call('a',1,'read_payables',{})
            self.assertTrue(flow.payables.settled)
            self.assertTrue(all(row['state']=='paid' for row in result['invoices']))
            event=next(e for e in flow.world.events if e['operation']=='payables_settlement')
            self.assertGreaterEqual(event['arguments']['elapsed_seconds'],0.05)
            self.assertTrue(timed.verify_world(self.plan,flow.world.events,flow.payables.root,'active')['valid'])
            flow.close_reconciliation()
    def test_finalize_before_settlement_never_invents_a_payment(self):
        self.assertFalse(self.flow.advance_business_time(599))
        with TemporaryDirectory() as tmp:
            root=Path(tmp);self.flow.world.operator=root;self.flow.finalize()
            result=timed.inspect(root/'delivery-files'/'payables')
            self.assertTrue(result['valid']);self.assertEqual(result['unpaid_count'],8)
            effect=timed.effects(root/'delivery-files'/'payables')
            self.assertTrue(effect['awaiting_settlement']);self.assertEqual(effect['outstanding_count'],8);self.assertEqual(effect['unpaid_count'],0)
            self.assertFalse((root/'delivery-files'/'payables'/'operations'/'settlement.csv').exists())
