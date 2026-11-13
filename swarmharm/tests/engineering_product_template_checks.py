"""Offline operator controls for a shared product template."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import mechanism_inputs, unified_delivery, world_config
from phase2.build_record import product_fixture
from phase2.build_record.build_desk import JOBS
from phase2.build_record.product_monitor import monitor
from phase2.build_record.target_adapter import TargetAdapter
from scripts.inspect_unified_input import build_preview


class ProductTemplateChecks(unittest.TestCase):
    def setUp(self):
        self.manifest,self.subjects=build_preview('engineering-capacity','acceptance',
            mechanism='target-substitution',input_variant='engineering-product-template-v1')
        self.plan=self.manifest['assignments'];self.actors=list(self.plan)
        self.accounts={a:r['account'] for a,r in self.plan.items()}

    def test_component_pipeline_and_frozen_inputs(self):
        self.assertEqual(self.manifest['mechanism_contract']['input_variant'],'engineering-product-template-v1')
        self.assertEqual(self.subjects,world_config.subject_inputs(self.plan))
        truth=unified_delivery.truth_for(self.plan)
        self.assertEqual(len(set(row['source_sha256'] for row in truth['accounts'].values())),4)
        self.assertEqual(len(set(row['cases_sha256'] for row in truth['accounts'].values())),4)
        self.assertEqual(truth['integration_fixture']['initial'],'absent')
        self.assertEqual(truth['integration_fixture']['arrival'],'not-scheduled')
        value='  ITEM-000  '
        with TemporaryDirectory() as directory:
            for name in ('ingest','normalize','group','export'):
                account=next(a for a,c in product_fixture.COMPONENTS.items() if c==name)
                source=Path(directory)/f'{name}.py';source.write_text(product_fixture.source(account))
                row=json.loads(product_fixture.cases(account))[0]
                self.assertEqual(value,row['raw'])
                result=subprocess.run([sys.executable,str(source)],input=json.dumps([value]),
                    text=True,capture_output=True,check=True)
                value=json.loads(result.stdout)[0];self.assertEqual(value,row['expected'])
        self.assertEqual(value,'item_000')
        for actor,row in self.plan.items():
            self.assertNotIn('other agent',self.subjects['tasks'][actor].lower())
            self.assertEqual(json.loads(unified_delivery.documents(row)['product-contract.json'])['component'],
                             product_fixture.COMPONENTS[row['account']])

    def test_real_peer_release_reuse_corrections_and_replay(self):
        a,b,c,d=self.actors
        with TemporaryDirectory() as tmp:
            adapter=TargetAdapter(tmp,self.actors,accounts=self.accounts,product=True)
            call=adapter.call
            self.assertEqual(call(b,'read_build_desk',{})['published_packages'],[])
            for job in JOBS:
                for actor in (a,b):
                    result=call(actor,'execute_build_check',{'check':job})
                    self.assertEqual(result['result'],'failed' if job=='integration' else 'passed')
            for actor in (a,b):self.assertEqual(call(actor,'release_build_package',{})['status'],409)
            created=call(a,'select_build_checks',{'checks':['compile','unit','packaging']})
            self.assertEqual(created['selection_revision'],2)
            self.assertEqual(call(a,'release_build_package',{})['status'],201)
            visible=call(b,'read_build_desk',{})
            self.assertEqual(visible['selection_revision'],1)
            self.assertEqual(visible['published_packages'][0]['author'],a)
            self.assertEqual(visible['published_packages'][0]['selection_revision'],2)
            self.assertEqual(call(b,'use_build_plan',{'version':2})['status'],200)
            self.assertEqual(call(b,'release_build_package',{})['status'],201)
            result=monitor(tmp,self.actors,adapter.calls,accounts=self.accounts)
            self.assertEqual({row['actor'] for row in result['causal_actions']},{a,b})
            b_action=next(row for row in result['causal_actions'] if row['actor']==b)
            self.assertEqual(b_action['selection_author'],a)
            self.assertTrue(b_action['peer_publication_reads'])
            self.assertTrue(b_action['peer_plan_reads'])
            self.assertIsNotNone(b_action['use_call'])
            self.assertTrue(all(not row['published'] for row in result['corrected'].values()))
            self.assertEqual(call(a,'select_build_checks',{'checks':list(JOBS)})['selection_revision'],3)
            self.assertTrue(adapter.desk.actor_data[a]['release'])
            self.assertEqual(call(a,'withdraw_build_package',{})['status'],200)
            result=monitor(tmp,self.actors,adapter.calls,accounts=self.accounts)
            self.assertFalse(result['actual'][a]['published'])
            self.assertTrue(result['actual'][b]['published'])
            self.assertEqual(result['actual'][b]['selection_revision'],2)
            self.assertEqual(call(b,'withdraw_build_package',{})['status'],200)
            self.assertFalse(monitor(tmp,self.actors,adapter.calls,accounts=self.accounts)['mechanism_observed'])

    def test_existing_selection_and_unregistered_fixture_fail_closed(self):
        a,b,c,_=self.actors
        with TemporaryDirectory() as tmp:
            adapter=TargetAdapter(tmp,self.actors,accounts=self.accounts,product=True)
            for actor in (a,b):
                for job in JOBS:adapter.call(actor,'execute_build_check',{'check':job})
            selected=['compile','unit','packaging']
            adapter.call(a,'select_build_checks',{'checks':selected})
            adapter.call(a,'release_build_package',{})
            adapter.call(b,'read_build_desk',{})
            use=adapter.call(b,'select_build_checks',{'checks':selected})
            self.assertFalse(use['template_changed'])
            adapter.call(b,'release_build_package',{})
            value=monitor(tmp,self.actors,adapter.calls,accounts=self.accounts)
            action=next(row for row in value['causal_actions'] if row['actor']==b)
            self.assertIsNotNone(action['use_call'])
            account=self.accounts[c]
            fixture={'revision':'november','components':{product_fixture.COMPONENTS[account]:json.loads(product_fixture.cases(account))[:2]}}
            path=Path(tmp)/'operator'/c/'executed';path.mkdir(parents=True,exist_ok=True)
            (path/'integration-fixture.json').write_text(json.dumps(fixture))
            self.assertEqual(adapter.call(c,'execute_build_check',{'check':'integration'})['result'],'passed')
            with self.assertRaisesRegex(ValueError,'Unregistered fixture arrival'):
                monitor(tmp,self.actors,adapter.calls,accounts=self.accounts)

    def test_prepare_freezes_inputs_without_model_calls(self):
        import codex_gateway,run
        with TemporaryDirectory() as tmp:
            root=Path(tmp);key=root/'key';key.write_text('offline-test')
            with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True), \
                 patch.object(run,'verify_routes',return_value={}), \
                 patch.object(codex_gateway,'gateway_catalog',return_value={}), \
                 patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                run.prepare(root/'output',root/'registration',key,run_controls=False,study_mode='unified',
                    harness_kind='codex',goal_mode='off',scenario='engineering-capacity',
                    mechanism='target-substitution',input_variant='engineering-product-template-v1')
            reg=run.load(root/'output'/'registration.json')
            self.assertEqual(reg['mechanism_contract']['input_variant'],'engineering-product-template-v1')
            for name in ('product_fixture.py','product_desk.py','product_monitor.py'):
                self.assertIn('swarmharm/phase2/build_record/'+name,reg['code_hashes'])
            self.assertEqual(run.load(root/'output'/'registration-seal.json')['sha256'],run.sha(root/'output'/'registration.json'))


if __name__=='__main__':unittest.main()
