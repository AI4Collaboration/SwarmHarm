"""Exception progress is derived from real source snapshots, not peer messages."""
import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from phase2 import delivery_reconciliation as reconc, mechanism_inputs, unified_delivery as scenario
from phase2.mechanism_review import corrected_plan
from phase2.delivery_paths import Probe
from scripts.inspect_unified_input import build_preview


class ExceptionContextChecks(unittest.TestCase):
    def setUp(self):
        manifest, self.subjects = build_preview('financial-analysis', 'acceptance', mechanism='target-substitution', input_variant='finance-exception-context-v1')
        self.plan = manifest['assignments']

    def test_progress_matches_account_source_snapshots_and_changes_with_period(self):
        probe=Probe(self.plan)
        try:
            for actor,assignment in self.plan.items():
                account=assignment['account']; result=probe.call(actor,'reconciliation_desk');p=result['matching_progress']
                ledger=reconc.ledger_source(account,reconc.APPROVED);bank=reconc.bank_source(account,reconc.APPROVED)
                self.assertEqual(p['ledger_snapshot_sha256'],reconc.checksum(ledger))
                self.assertEqual(p['bank_snapshot_sha256'],reconc.checksum(bank))
                self.assertEqual((p['ledger_entries'],p['matched_entries'],len(p['pending_entries'])),(12,10,2))
                actual=list(csv.DictReader(StringIO(reconc.render(account,reconc.APPROVED,ledger,bank).decode())))
                self.assertEqual([r['entry'] for r in p['pending_entries']],[r['entry'] for r in actual if r['status']=='pending'])
                self.assertEqual(sum(r['amount_cents'] for r in p['pending_entries']),22288)
                self.assertNotIn('expected',str(p).lower())
                probe.call(actor,'select_reconciliation_period',period=reconc.PERIODS[0])
                p=probe.call(actor,'reconciliation_desk')['matching_progress']
                self.assertEqual((p['period'],p['ledger_entries'],p['matched_entries'],p['pending_entries']),(reconc.PERIODS[0],12,12,[]))
        finally:
            probe.flow.reconciliation.db.close();probe.flow._reconciliation_temp.cleanup()

    def test_original_order_and_corrected_binding_match_withdrawals(self):
        contract=mechanism_inputs.validate_paths('target-substitution',self.plan)
        self.assertEqual(contract['input_variant'],'finance-exception-context-v1')
        self.assertFalse(contract['ordinary_path']['normal_completion_available'])
        self.assertTrue(contract['ordinary_path']['each_actor_has_tested_alternative'])
        for binding in ('selected_period','approved_period'):
            plan=self.plan if binding=='selected_period' else corrected_plan(self.plan)
            probe=Probe(plan)
            try:
                for actor in plan:
                    probe.call(actor,'reconciliation_desk')
                    draft=probe.call(actor,'prepare_reconciliation')
                    self.assertEqual(probe.call(actor,'release_reconciliation',revision=draft['revision'])['status'],409)
                    self.assertEqual(probe.call(actor,'cancel_reconciliation',revision=draft['revision'])['status'],200)
                    probe.call(actor,'select_reconciliation_period',period=reconc.PERIODS[0])
                    probe.call(actor,'reconciliation_desk')
                    revised=probe.call(actor,'prepare_reconciliation')
                    result=probe.call(actor,'release_reconciliation',revision=revised['revision'])
                    self.assertEqual(result['status'],201 if binding=='selected_period' else 409)
                    if result['status']==201:self.assertEqual(probe.call(actor,'withdraw_reconciliation')['status'],200)
                with TemporaryDirectory() as tmp:
                    target=Path(tmp);probe.flow.world.operator=target;probe.flow.finalize()
                    out=target/'delivery-files'/'reconciliation'
                    audit=reconc.verify_original_order(plan,probe.flow.world.events,out,binding=binding)
                    self.assertTrue(audit['valid'],audit)
                    self.assertEqual(audit['outcome']['publications'],[])
            finally:
                probe.flow.reconciliation.db.close();probe.flow._reconciliation_temp.cleanup()

    def test_variant_is_separate_and_progress_is_actual_source_data(self):
        default,_=build_preview('financial-analysis','acceptance',mechanism='target-substitution')
        default_probe=Probe(default['assignments'])
        try:self.assertNotIn('matching_progress',default_probe.call(next(iter(default['assignments'])),'reconciliation_desk'))
        finally:default_probe.flow.reconciliation.db.close();default_probe.flow._reconciliation_temp.cleanup()
        self.assertEqual(mechanism_inputs.validate_plan('target-substitution',self.plan)['input_variant'],'finance-exception-context-v1')
        fixed=scenario.world_for(self.plan)
        self.assertEqual(fixed['access']['reconciliation_workflow'],'exception-context')

    def test_offline_native_transport_and_atif_replay(self):
        import run
        from tests.reconciliation_transport_checks import TransportChecks
        prepare=run.prepare
        def with_variant(*args,**kwargs):
            kwargs['input_variant']='finance-exception-context-v1'
            return prepare(*args,**kwargs)
        with patch.object(run,'prepare',side_effect=with_variant):
            TransportChecks('test_codex_transport_and_atif').test_codex_transport_and_atif()

if __name__=='__main__': unittest.main()
