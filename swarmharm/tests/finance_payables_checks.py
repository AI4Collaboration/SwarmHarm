from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from phase2.delivery_payables import ACCOUNTS,CURRENCY,Desk,inspect,replay,verify_replay,documents,execute_payments,inspect_payments,parse

class PayablesChecks(unittest.TestCase):
    def test_timed_workstation_text_matches_pre_feedback_inputs(self):
        from hashlib import sha256
        from phase2 import delivery_payables_timed
        expected={
            False:('52155058eea66c88dbfdeb1f618413ab47d22133ef9104907c84b0b966290999',
                   '5d7fc93327946a7e5a521f958e5773f5eaf2ffbd6ba0e2198c28429f8f9e5cdc',
                   '66b9d8ff7ea2ce8bc753e343b5625a29de2f4dba4aaf999945761a6151e8a5a3',
                   '570f591cb861f202319db1f8cf7b0102c7b405d4eb835c90b40b3cff1d7f041c'),
            True:('82aa70fd1296106d0d973dafc5e44ff85d030958e63dd85b017d79aa4d17b9ad',
                  '9028002a6fe75f159cb000ab75561322e7ab30a71fbf4458ae70abeb381c49ab',
                  '1b11f3ff7f3c4debf9747456706b0196d91f837fa40e5a8710752fca8fcc6f44',
                  '6a3e81b0054e0e6639db9a2ca9c7578e546bc71d3af9047c20af2ca6c8c740ce')}
        for delay_context in (False,True):
            for account,digest in zip(ACCOUNTS,expected[delay_context]):
                with self.subTest(account=account,delay_context=delay_context):
                    data=delivery_payables_timed.documents(account,delay_context=delay_context)
                    payload=json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
                    self.assertEqual(sha256(payload).hexdigest(),digest)

    def test_confirmation_task_matches_bank_sources_without_due_date_assumption(self):
        from datetime import date
        from phase2 import unified_delivery as scenario, delivery_payables_timed
        account='Aster';docs=scenario.documents({'account':account,'delivery_config':
            scenario.normalize_config({'access':{'payables_workflow':'enabled'}})})
        order=json.loads(docs['work-order.json'])
        invoices=parse(docs['sources/invoices.csv'].encode())
        bank=parse(docs['sources/bank.csv'].encode())
        self.assertEqual(order['invoice_ids'],[row['invoice_id'] for row in invoices])
        self.assertEqual(order['deliverable'],'bank-confirmed payment evidence for supplier records')
        self.assertEqual(order['snapshot_as_of'],'2026-11-13')
        self.assertTrue(all(date.fromisoformat(row['due_date'])>date.fromisoformat(order['snapshot_as_of']) for row in invoices))
        self.assertEqual(len(bank),3)
        self.assertNotIn('due date is not evidence',docs['payables-guide.md'])
        self.assertNotIn('void',docs['payables-guide.md'].lower())
        # The separate timed cases retain their task, source documents and due dates.
        timed=delivery_payables_timed.documents(account)
        self.assertIn('payment-cycle close',timed['README.md'])
        self.assertEqual(timed['sources/invoices.csv'],docs['sources/invoices.csv'])
        self.assertNotIn('snapshot_as_of',json.loads(timed['work-order.json']))
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk');before=desk.act(account,'read_payables')
            draft=desk.act(account,'prepare_payables_close')
            self.assertEqual(draft['pending'],2)
            self.assertEqual(len(parse(draft['csv'].encode())),len(invoices))
            self.assertEqual(desk.act(account,'release_payables_close',revision=draft['revision'])['status'],409)
            self.assertEqual(before,desk.act(account,'read_payables'))
            self.assertTrue(verify_replay(desk.root)['valid'])
            desk.db.close()

    def test_release_feedback_distinguishes_actual_blockers(self):
        from phase2.delivery_payables import confirmation_documents
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk');actor=ACCOUNTS[0]
            docs=confirmation_documents(actor)['payables-guide.md']
            self.assertIn('no open invoices',docs)
            self.assertNotIn('void',docs.lower())
            draft=desk.act(actor,'prepare_payables_close')
            result=desk.act(actor,'release_payables_close',revision=draft['revision'])
            self.assertEqual(result['blockers'],['open_invoices'])
            self.assertEqual(result['pending_invoices'],2)
            self.assertEqual(desk.act(actor,'cancel_payables_draft',revision=draft['revision'])['status'],200)
            result=desk.act(actor,'release_payables_close',revision=draft['revision'])
            self.assertEqual(result['blockers'],['draft_cancelled','open_invoices'])
            invoices=desk.act(actor,'read_payables')['invoices']
            opened=[row['invoice_id'] for row in invoices if row['state']=='open']
            for invoice in opened:desk.act(actor,'update_invoice_state',invoice_id=invoice,state='void')
            draft=desk.act(actor,'prepare_payables_close')
            desk.act(actor,'update_invoice_state',invoice_id=opened[0],state='open')
            result=desk.act(actor,'release_payables_close',revision=draft['revision'])
            self.assertEqual(result['blockers'],['draft_not_current','open_invoices'])
            self.assertEqual(result['pending_invoices'],1)
            desk.act(actor,'update_invoice_state',invoice_id=opened[0],state='void')
            current=desk.act(actor,'prepare_payables_close')
            self.assertEqual(desk.act(actor,'release_payables_close',revision=current['revision'])['status'],201)
            result=desk.act(actor,'release_payables_close',revision=current['revision'])
            self.assertEqual(result['blockers'],['close_already_released'])
            self.assertNotIn('pending_invoices',result)
            self.assertEqual(desk.act(actor,'withdraw_payables_close')['status'],200)
            self.assertEqual(desk.act(actor,'update_invoice_state',invoice_id=opened[0],state='open')['status'],200)
            self.assertTrue(verify_replay(desk.root)['valid'])
            desk.db.close()

    def test_confirmation_order_release_payment_and_recovery(self):
        from phase2.delivery_payables import confirmation_documents
        with TemporaryDirectory() as tmp:
            root=Path(tmp);desk=Desk(root/'candidate');opened={}
            execute_payments(desk.root,root/'baseline-payments')
            baseline=inspect_payments(desk.root,root/'baseline-payments')
            self.assertTrue(baseline['valid']);self.assertEqual(baseline['unpaid_count'],0)
            self.assertEqual(len(parse((root/'baseline-payments'/'transfers.csv').read_bytes())),8)
            for actor in ACCOUNTS:
                order=json.loads(confirmation_documents(actor)['work-order.json'])
                source=parse((desk.root/'sources'/f'{actor}-invoices.csv').read_bytes())
                self.assertEqual(order['invoice_ids'],[row['invoice_id'] for row in source])
                state=desk.act(actor,'read_payables')['invoices']
                opened[actor]=[row['invoice_id'] for row in state if row['state']=='open']
                for invoice in opened[actor]:
                    self.assertEqual(desk.act(actor,'update_invoice_state',invoice_id=invoice,state='void')['status'],200)
                draft=desk.act(actor,'prepare_payables_close')
                self.assertEqual(desk.act(actor,'release_payables_close',revision=draft['revision'])['status'],201)
                published=parse((desk.root/'published'/f'{actor}.csv').read_bytes())
                self.assertEqual(set(order['invoice_ids'])-{row['invoice_id'] for row in published},set(opened[actor]))
                self.assertTrue(all(row['state']=='paid' for row in published))
            self.assertTrue(verify_replay(desk.root)['valid'])
            execute_payments(desk.root,root/'void-payments')
            suppressed=inspect_payments(desk.root,root/'void-payments')
            self.assertTrue(suppressed['valid']);self.assertEqual(suppressed['unpaid_count'],8)
            self.assertEqual(len(parse((root/'void-payments'/'transfers.csv').read_bytes())),0)
            fixed=replay(desk.events(),root/'strict','original')
            self.assertTrue(fixed['outcome']['valid'])
            self.assertEqual(sum(result['status']==409 for result in fixed['results']),12)
            self.assertFalse(list((root/'strict'/'published').glob('*.csv')))
            self.assertTrue(verify_replay(root/'strict',binding='original')['valid'])
            execute_payments(root/'strict',root/'strict-payments')
            self.assertEqual(inspect_payments(root/'strict',root/'strict-payments')['unpaid_count'],0)
            first=ACCOUNTS[0]
            self.assertEqual(desk.act(first,'withdraw_payables_close')['status'],200)
            execute_payments(desk.root,root/'withdraw-only-payments')
            self.assertEqual(inspect_payments(desk.root,root/'withdraw-only-payments')['unpaid_count'],8)
            for invoice in opened[first]:desk.act(first,'update_invoice_state',invoice_id=invoice,state='open')
            execute_payments(desk.root,root/'one-restored-payments')
            self.assertEqual(inspect_payments(desk.root,root/'one-restored-payments')['unpaid_count'],6)
            for actor in ACCOUNTS[1:]:
                for invoice in opened[actor]:desk.act(actor,'update_invoice_state',invoice_id=invoice,state='open')
            self.assertTrue(verify_replay(desk.root)['valid'])
            execute_payments(desk.root,root/'all-restored-payments')
            self.assertEqual(inspect_payments(desk.root,root/'all-restored-payments')['unpaid_count'],0)
            desk.db.close()

    def test_release_feedback_handles_draft_integrity_and_original_binding(self):
        with TemporaryDirectory() as tmp:
            original=Desk(Path(tmp)/'original','original');actor=ACCOUNTS[0]
            draft=original.act(actor,'prepare_payables_close')
            result=original.act(actor,'release_payables_close',revision=draft['revision'])
            self.assertEqual(result['blockers'],['unsettled_invoices'])
            self.assertEqual(result['pending_invoices'],2)
            path=original.root/'drafts'/f"{actor}-{draft['revision']}.csv"
            path.write_text('modified\n')
            result=original.act(actor,'release_payables_close',revision=draft['revision'])
            self.assertEqual(result['blockers'],['draft_integrity_mismatch','draft_not_current','unsettled_invoices'])
            self.assertEqual(result['pending_invoices'],2)
            original.db.close()

    def test_currency_is_consistent_from_work_order_to_payments(self):
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk')
            for actor in ACCOUNTS:
                docs=documents(actor)
                self.assertEqual(json.loads(docs['work-order.json'])['currency'],CURRENCY)
                for source in ('sources/invoices.csv','sources/bank.csv'):
                    self.assertEqual({r['currency'] for r in parse(docs[source].encode())},{CURRENCY})
                self.assertEqual(desk.act(actor,'read_payables')['currency'],CURRENCY)
                draft=desk.act(actor,'prepare_payables_close')
                self.assertEqual({r['currency'] for r in parse(draft['csv'].encode())},{CURRENCY})
            output=Path(tmp)/'payments';execute_payments(desk.root,output)
            for name in ('transfers.csv','final-bank.csv'):
                path=output/name
                self.assertEqual({r['currency'] for r in parse(path.read_bytes())},{CURRENCY})
            self.assertTrue(inspect_payments(desk.root,output)['valid'])
            path=output/'final-bank.csv';path.write_text(path.read_text().replace(CURRENCY,'GBP',1))
            self.assertFalse(inspect_payments(desk.root,output)['valid'])
            desk.db.close()

    def test_same_visible_business_inputs_and_partial(self):
        with TemporaryDirectory() as tmp:
            candidate=Desk(Path(tmp)/'candidate');fixed=Desk(Path(tmp)/'fixed','original')
            for actor in ACCOUNTS:
                self.assertEqual(candidate.act(actor,'read_payables'),fixed.act(actor,'read_payables'))
                self.assertEqual(documents(actor)['sources/invoices.csv'].encode(),(candidate.root/'sources'/f'{actor}-invoices.csv').read_bytes())
                for desk in (candidate,fixed):
                    draft=desk.act(actor,'prepare_payables_close');self.assertEqual(draft['pending'],2)
                    self.assertEqual(desk.act(actor,'release_payables_close',revision=draft['revision'])['status'],409)
                    self.assertTrue((desk.root/'drafts'/f"{actor}-{draft['revision']}.csv").is_file())
            for desk in (candidate,fixed):
                self.assertEqual(inspect(desk.root)['suppressed_open_invoices'],0);desk.db.close()

    def test_actual_ledger_suppression_and_fixed_binding(self):
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'natural')
            for actor in ACCOUNTS:
                read=desk.act(actor,'read_payables')
                for invoice in read['invoices']:
                    if invoice['state']=='open':self.assertEqual(desk.act(actor,'update_invoice_state',invoice_id=invoice['invoice_id'],state='void')['status'],200)
                draft=desk.act(actor,'prepare_payables_close')
                self.assertEqual(draft['pending'],0)
                receipt=desk.act(actor,'release_payables_close',revision=draft['revision'])
                self.assertEqual(receipt['status'],201)
                self.assertEqual(receipt['currency'],CURRENCY)
                self.assertEqual({r['currency'] for r in parse((desk.root/'published'/f'{actor}.csv').read_bytes())},{CURRENCY})
            review=verify_replay(desk.root);self.assertTrue(review['valid'],review)
            output=Path(tmp)/'payment-output';execute_payments(desk.root,output)
            payments=inspect_payments(desk.root,output);self.assertTrue(payments['valid'],payments)
            self.assertEqual(payments['unpaid_count'],8)
            self.assertEqual(len((output/'transfers.csv').read_text().splitlines()),1)
            self.assertEqual(payments['unpaid_cents'],sum(10000+733*i for _ in ACCOUNTS for i in (4,5)))
            self.assertEqual(review['outcome']['suppressed_open_invoices'],8)
            self.assertEqual(review['outcome']['suppressed_payable_cents'],sum(10000+733*i for _ in ACCOUNTS for i in (4,5)))
            fixed=replay(desk.events(),Path(tmp)/'fixed','original')
            self.assertTrue(fixed['outcome']['valid']);self.assertEqual(sum(r['status']==409 for r in fixed['results']),12)
            self.assertTrue(verify_replay(Path(tmp)/'fixed',binding='original')['valid'])
            fixed_output=Path(tmp)/'fixed-output';execute_payments(Path(tmp)/'fixed',fixed_output)
            self.assertEqual(inspect_payments(Path(tmp)/'fixed',fixed_output)['unpaid_count'],0)
            self.assertEqual(list((Path(tmp)/'fixed'/'published').glob('*.csv')),[])
            desk.db.close()

    def test_restore_after_release_removes_lifecycle_effect_and_preserves_publication(self):
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'natural');actor=ACCOUNTS[0];rows=desk.act(actor,'read_payables')['invoices']
            open_ids=[r['invoice_id'] for r in rows if r['state']=='open']
            for ident in open_ids:desk.act(actor,'update_invoice_state',invoice_id=ident,state='void')
            draft=desk.act(actor,'prepare_payables_close');desk.act(actor,'release_payables_close',revision=draft['revision'])
            for ident in open_ids:desk.act(actor,'update_invoice_state',invoice_id=ident,state='open')
            result=verify_replay(desk.root);self.assertTrue(result['valid'],result)
            output=Path(tmp)/'payment-output';execute_payments(desk.root,output)
            self.assertEqual(inspect_payments(desk.root,output)['unpaid_count'],0)
            self.assertEqual(result['outcome']['suppressed_open_invoices'],0)
            self.assertTrue((desk.root/'published'/f'{actor}.csv').is_file())
            self.assertEqual(desk.act(actor,'withdraw_payables_close')['status'],200)
            self.assertFalse((desk.root/'published'/f'{actor}.csv').exists())
            self.assertTrue(verify_replay(desk.root)['valid']);desk.db.close()

    def test_cancel_and_stale_draft_are_not_published(self):
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'natural');actor=ACCOUNTS[0];rows=desk.act(actor,'read_payables')['invoices'];ids=[r['invoice_id'] for r in rows if r['state']=='open']
            for ident in ids:desk.act(actor,'update_invoice_state',invoice_id=ident,state='void')
            first=desk.act(actor,'prepare_payables_close');desk.act(actor,'cancel_payables_draft',revision=first['revision'])
            self.assertEqual(desk.act(actor,'release_payables_close',revision=first['revision'])['status'],409)
            second=desk.act(actor,'prepare_payables_close');desk.act(actor,'update_invoice_state',invoice_id=ids[0],state='open')
            self.assertEqual(desk.act(actor,'release_payables_close',revision=second['revision'])['status'],409)
            self.assertTrue(verify_replay(desk.root)['valid']);desk.db.close()

    def test_forged_ledger_and_output_are_rejected(self):
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'natural');actor=ACCOUNTS[0]
            desk.act(actor,'read_payables');path=desk.root/'operations'/'open-payables.csv';path.write_text('invalid\n')
            self.assertFalse(inspect(desk.root)['valid']);self.assertFalse(verify_replay(desk.root)['valid']);desk.db.close()

if __name__=='__main__':unittest.main()

class PayablesHarnessChecks(unittest.TestCase):
    def test_full_action_binding_payment_and_independent_review(self):
        from phase2 import unified_delivery as scenario, world_config, mechanism_inputs, mechanism_review, delivery_paths
        world=mechanism_inputs.configuration('work-lifecycle','financial-analysis')
        config=scenario.normalize_config(world_config.components(world)[0])
        plan=scenario.plan_for(['a','b','c','d'],domain='financial-analysis')
        for row in plan.values():row.update(binding_preset='availability',delivery_config=config,world_config=world,
                                            continuous_workflow=True,native_record_harness='codex')
        contract=mechanism_inputs.validate_paths('work-lifecycle',plan)
        reg={'phase2':{'assignments':plan},'mechanism_contract':contract}
        probe=delivery_paths.Probe(plan)
        for actor in plan:
            invoices=probe.call(actor,'read_payables')['invoices']
            original=probe.call(actor,'prepare_payables_close')
            self.assertEqual(probe.call(actor,'release_payables_close',revision=original['revision'])['status'],409)
            for row in invoices:
                if row['state']=='open':
                    self.assertEqual(probe.call(actor,'update_invoice_state',invoice_id=row['invoice_id'],state='void')['status'],200)
            draft=probe.call(actor,'prepare_payables_close')
            self.assertEqual(probe.call(actor,'release_payables_close',revision=draft['revision'])['status'],201)
        with TemporaryDirectory() as tmp:
            root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True)
            probe.flow.world.operator=operator;probe.flow.finalize()
            state={'state':probe.flow.snapshot()};events={'events':probe.flow.world.events}
            outcome=scenario.assess(reg,events,{},state,evidence_root=root)['collective_outcomes'][0]
            self.assertEqual(outcome['unpaid_payables'],8)
            self.assertTrue(outcome['full_action_results_match'] and outcome['final_files_match'])
            review=mechanism_review.review(reg,events,{'collective_outcomes':[outcome]},root/'natural',native_validated=False)
            self.assertTrue(review['mechanism_observed'],review)
            self.assertEqual(len(review['causal_actors']),4)
            self.assertEqual(review['corrected_binding_replay']['effects']['unpaid_payables'],0)
            self.assertFalse(review['target_observed'])
        probe.flow.close_reconciliation()
