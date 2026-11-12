from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2.delivery_payables import ACCOUNTS,Desk,inspect,replay,verify_replay,documents,execute_payments,inspect_payments

class PayablesChecks(unittest.TestCase):
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
                self.assertEqual(desk.act(actor,'release_payables_close',revision=draft['revision'])['status'],201)
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
