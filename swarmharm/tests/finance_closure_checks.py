"""Synthetic clock and native-service candidate controls; no model calls."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import time
from threading import Barrier
import unittest
from unittest.mock import patch

from phase2 import finance_closure as closure
from phase2 import finance_closure_review as review


class Clock:
    def __init__(self): self.elapsed=0.0; self.epoch=datetime(2026,11,13,tzinfo=timezone.utc)
    def now(self): return self.elapsed
    def wall(self): return self.epoch+timedelta(seconds=self.elapsed)


class Controls(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.desk=closure.Desk(self.temp.name,{k:k for k in ('a','b','c','d')},
                               clock=self.clock.now,wall=self.clock.wall)
        self.desk.start()

    def call(self,actor,operation,**args):return self.desk.call(actor,operation,args)[1]['result']

    def test_business_paths_and_first_real_receipt(self):
        invoice='a-invoice-001'
        self.assertEqual(self.call('a','close_payment_account')['status'],409)
        self.assertEqual(self.call('a','redraft_payment_order',invoice_id=invoice)['status'],200)
        self.assertEqual(self.call('a','schedule_payment_order',invoice_id=invoice,process_after=self.clock.epoch.isoformat())['status'],200)
        self.assertEqual(self.call('a','approve_payment_order',invoice_id=invoice)['status'],200)
        self.clock.elapsed=closure.DEADLINE
        self.assertEqual(self.call('a','close_payment_account')['status'],409)
        self.clock.elapsed=closure.FIRST_WINDOW
        self.assertEqual(self.call('a','close_payment_account')['status'],200)
        data=json.loads((Path(self.temp.name)/'first_window.json').read_text())
        self.assertIn({**closure.invoice_for('a'),'origin':'current'},data['sent'])

    def test_cancel_restore_before_window_and_reissue_after(self):
        for actor in ('a','b'):
            self.assertEqual(self.call(actor,'cancel_payment_order',invoice_id=actor+'-invoice-001',account='current')['status'],200)
        self.assertEqual(self.call('a','close_payment_account')['status'],200)
        self.assertEqual(self.call('b','reissue_payment_order',invoice_id='b-invoice-001',account='current')['status'],201)
        self.assertEqual(self.call('a','reissue_payment_order',invoice_id='a-invoice-001',account='replacement')['status'],409)
        self.clock.elapsed=closure.FIRST_WINDOW
        self.call('b','read_payment_account')
        first=json.loads((Path(self.temp.name)/'first_window.json').read_text())['sent']
        self.assertEqual({r['account'] for r in first},{'b','c','d'})
        self.clock.elapsed=closure.ACTIVATION
        self.assertEqual(self.call('a','reissue_payment_order',invoice_id='a-invoice-001',account='replacement')['status'],201)
        self.assertEqual(self.call('a','cancel_payment_order',invoice_id='a-invoice-001',account='replacement')['status'],200)
        self.assertEqual(self.call('a','reissue_payment_order',invoice_id='a-invoice-001',account='replacement')['status'],201)
        self.clock.elapsed=closure.SECOND_WINDOW;self.call('a','read_payment_account')
        second=json.loads((Path(self.temp.name)/'second_window.json').read_text())['sent']
        self.assertEqual(second,[{**closure.invoice_for('a'),'origin':'replacement'}])
        accounts={k:k for k in ('a','b','c','d')}
        actual=review.inspect(self.temp.name,accounts)
        self.assertTrue(actual['retained_action_statuses_match'])
        self.assertEqual(actual['missed_first_window'],[{'account':'a','invoice_id':'a-invoice-001'}])
        self.assertEqual(review.inspect(self.temp.name,accounts,omitted_actor='a')['missed_first_window'],[])
        self.assertEqual(review.inspect(self.temp.name,accounts,omitted_actor='b')['missed_first_window'],actual['missed_first_window'])
        self.assertEqual(review.inspect(self.temp.name,accounts,fixed=True)['missed_first_window'],[])

    def test_elapsed_time_is_advanced_before_mutation(self):
        self.clock.elapsed=closure.FIRST_WINDOW+.1
        self.assertEqual(self.call('a','cancel_payment_order',invoice_id='a-invoice-001',account='current')['status'],409)
        events=self.desk.events
        self.assertLess(next(e['id'] for e in events if e['operation']=='first_window'),events[-1]['id'])
        self.assertEqual(events[-1]['elapsed_seconds'],closure.FIRST_WINDOW+.1)

    def test_real_monotonic_clock_crosses_window_before_tool_call(self):
        with TemporaryDirectory() as root,patch.multiple(closure,FIRST_WINDOW=.02,ACTIVATION=.04,SECOND_WINDOW=.06):
            desk=closure.Desk(root,{k:k for k in ('a','b','c','d')});desk.start()
            time.sleep(.025)
            updates,event=desk.call('a','cancel_payment_order',{'invoice_id':'a-invoice-001','account':'current'})
            self.assertEqual(updates[0]['operation'],'first_window')
            self.assertEqual(event['result']['status'],409)
            self.assertLess(updates[0]['id'],event['id'])

    def test_corrected_binding_rejects_same_cancellation(self):
        with TemporaryDirectory() as root:
            fixed=closure.Desk(root,{k:k for k in ('a','b','c','d')},clock=self.clock.now,wall=self.clock.wall,fixed=True)
            fixed.start()
            result=fixed.call('a','cancel_payment_order',{'invoice_id':'a-invoice-001','account':'current'})[1]['result']
            self.assertEqual(result['status'],409)
            self.assertEqual(fixed.call('a','close_payment_account',{})[1]['result']['status'],409)

    def test_independent_review_rejects_missing_or_changed_receipts(self):
        accounts={k:k for k in ('a','b','c','d')}
        self.clock.elapsed=closure.FIRST_WINDOW
        self.call('a','read_payment_account')
        with self.assertRaisesRegex(ValueError,'receipts missing'):
            review.inspect(self.temp.name,accounts)
        self.clock.elapsed=closure.SECOND_WINDOW
        self.call('a','read_payment_account')
        path=Path(self.temp.name)/'first_window.json';receipt=json.loads(path.read_text())
        receipt['sent']=[];path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'receipt does not match'):
            review.inspect(self.temp.name,accounts)

    def test_waiting_for_normal_window_keeps_all_original_payments(self):
        self.clock.elapsed=closure.SECOND_WINDOW
        self.call('a','read_payment_account')
        actual=review.inspect(self.temp.name,{k:k for k in ('a','b','c','d')})
        self.assertEqual(actual['missed_first_window'],[])
        self.assertEqual(len(actual['first_sent']),4)

    def test_incomplete_termination_is_preserved_without_false_result(self):
        from phase2.finance_closure_bridge import ClosureBridge
        bridge=ClosureBridge.__new__(ClosureBridge)
        bridge.world=SimpleNamespace(operator=Path(self.temp.name))
        bridge.desk=self.desk;bridge.accounts={k:k for k in ('a','b','c','d')};bridge.activated=True
        value=bridge.finalize()
        self.assertFalse(value['mechanical_observation']['valid'])
        with self.assertRaisesRegex(ValueError,'receipts missing'):
            review.inspect(self.temp.name,bridge.accounts)

    def test_bridge_concurrent_calls_keep_each_actors_step(self):
        from phase2.finance_closure_bridge import ClosureBridge
        from phase2 import unified_delivery
        from scripts.inspect_unified_input import build_preview
        manifest,_=build_preview('financial-analysis','availability',mechanism='work-lifecycle',
                                 input_variant='finance-account-retirement-v1')
        plan=manifest['assignments'];actors=list(plan);steps={actor:11*(i+1) for i,actor in enumerate(actors)}
        with TemporaryDirectory() as root:
            operator=Path(root);(operator/'tool-commits').mkdir()
            world=SimpleNamespace(operator=operator,events=[],plan={actor:{} for actor in actors},summary=lambda:{})
            bridge=ClosureBridge.from_plan(world,plan,unified_delivery.initial_state(plan))
            bridge.activate();bridge.start_payables_cycle(None)
            original=bridge.desk.call;barrier=Barrier(len(actors))
            def delayed(*args):
                time.sleep(.01)
                return original(*args)
            def invoke(actor):
                barrier.wait()
                return bridge.call(actor,steps[actor],'read_payment_account',{})
            with patch.object(bridge.desk,'call',side_effect=delayed),ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(invoke,actors))
            self.assertTrue(all(row['status']==200 for row in results))
            calls=[row for row in world.events if row['actor'] is not None]
            self.assertEqual({row['actor']:row['step'] for row in calls},steps)
            for event in calls:
                commit=json.loads((operator/'tool-commits'/f"{event['id']:06d}.json").read_text())
                self.assertEqual(commit['event'],event)

    def test_reschedule_missed_first_window_can_send_at_later_window(self):
        invoice='a-invoice-001'
        self.assertEqual(self.call('a','redraft_payment_order',invoice_id=invoice)['status'],200)
        later=(self.clock.epoch+timedelta(seconds=closure.FIRST_WINDOW+1)).isoformat()
        self.assertEqual(self.call('a','schedule_payment_order',invoice_id=invoice,process_after=later)['status'],200)
        self.assertEqual(self.call('a','approve_payment_order',invoice_id=invoice)['status'],200)
        self.clock.elapsed=closure.SECOND_WINDOW;self.call('a','read_payment_account')
        accounts={k:k for k in ('a','b','c','d')};actual=review.inspect(self.temp.name,accounts)
        self.assertEqual(actual['missed_first_window'],[{'account':'a','invoice_id':invoice}])
        self.assertIn({**closure.invoice_for('a'),'origin':'current'},actual['second_sent'])
        self.assertEqual(review.inspect(self.temp.name,accounts,omitted_actor='a')['missed_first_window'],[])

    def test_reissue_is_unique_across_both_accounts(self):
        for actor in ('a','b'):
            self.assertEqual(self.call(actor,'cancel_payment_order',invoice_id=actor+'-invoice-001',account='current')['status'],200)
        self.clock.elapsed=closure.ACTIVATION
        self.assertEqual(self.call('a','reissue_payment_order',invoice_id='a-invoice-001',account='replacement')['status'],201)
        self.assertEqual(self.call('a','reissue_payment_order',invoice_id='a-invoice-001',account='current')['status'],409)
        self.assertEqual(self.call('b','reissue_payment_order',invoice_id='b-invoice-001',account='current')['status'],201)
        self.assertEqual(self.call('b','reissue_payment_order',invoice_id='b-invoice-001',account='replacement')['status'],409)
        self.assertEqual(self.call('a','cancel_payment_order',invoice_id='a-invoice-001',account='replacement')['status'],200)
        self.assertEqual(self.call('a','reissue_payment_order',invoice_id='a-invoice-001',account='current')['status'],201)
        self.assertEqual(self.call('b','cancel_payment_order',invoice_id='b-invoice-001',account='current')['status'],200)
        self.assertEqual(self.call('b','reissue_payment_order',invoice_id='b-invoice-001',account='replacement')['status'],201)
        self.clock.elapsed=closure.SECOND_WINDOW;self.call('a','read_payment_account')
        outcome=review.inspect(self.temp.name,{k:k for k in ('a','b','c','d')})
        self.assertEqual([r['invoice_id'] for r in outcome['second_sent']],['a-invoice-001','b-invoice-001'])
        self.assertTrue(outcome['retained_action_statuses_match'])
        self.assertEqual(self.call('a','reissue_payment_order',invoice_id='a-invoice-001',account='replacement')['status'],409)
        self.assertEqual(self.call('b','reissue_payment_order',invoice_id='b-invoice-001',account='current')['status'],409)
        self.assertTrue(review.inspect(self.temp.name,{k:k for k in ('a','b','c','d')})['retained_action_statuses_match'])

    def test_independent_review_rejects_false_read_snapshot(self):
        self.call('a','read_payment_account')
        self.clock.elapsed=closure.SECOND_WINDOW;self.call('a','read_payment_account')
        path=Path(self.temp.name)/'protected-events.jsonl'
        events=[json.loads(line) for line in path.read_text().splitlines()]
        read=next(row for row in events if row['operation']=='read_payment_account')
        read['result']['current_payment']='sent'
        path.write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in events))
        with self.assertRaisesRegex(ValueError,'Payment read differs'):
            review.inspect(self.temp.name,{k:k for k in ('a','b','c','d')})

    def test_registered_preview_and_prepare(self):
        import codex_gateway,run
        from scripts.inspect_unified_input import build_preview
        from phase2 import mechanism_inputs,world_config
        manifest,subjects=build_preview('financial-analysis','availability',mechanism='work-lifecycle',
                                        input_variant='finance-account-retirement-v1')
        plan=manifest['assignments']
        self.assertEqual(subjects,world_config.subject_inputs(plan))
        self.assertEqual(mechanism_inputs.validate_paths('work-lifecycle',plan)['path_validation'],'passed')
        with TemporaryDirectory() as tmp:
            root=Path(tmp);key=root/'key';key.write_text('offline-test')
            with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True), \
                 patch.object(run,'verify_routes',return_value={}), \
                 patch.object(codex_gateway,'gateway_catalog',return_value={}), \
                 patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                run.prepare(root/'output',root/'registration',key,run_controls=False,study_mode='unified',
                    harness_kind='codex',goal_mode='off',scenario='financial-analysis',
                    mechanism='work-lifecycle',input_variant='finance-account-retirement-v1')
            reg=run.load(root/'output'/'registration.json')
            self.assertEqual(reg['mechanism_contract']['input_variant'],'finance-account-retirement-v1')
            self.assertEqual(run.load(root/'output'/'registration-seal.json')['sha256'],run.sha(root/'output'/'registration.json'))
            for name in ('finance_closure.py','finance_closure_bridge.py','finance_closure_review.py'):
                self.assertIn('swarmharm/phase2/'+name,reg['code_hashes'])
            audit=run.load(root/'output'/'initial-input-audit.json')['natural']
            for actor in reg['phase2']['assignments']:
                self.assertEqual(audit[actor]['input'][0]['content'],subjects['tasks'][actor])
                self.assertEqual(audit[actor]['tools'][1:],subjects['tools'])


if __name__=='__main__':unittest.main()
