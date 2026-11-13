"""Scripted native Codex transport and independent review; no model behavior."""
from copy import deepcopy
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import threading
import unittest

import codex_gateway, export_atif, review, run
from phase2 import claim_evidence, mechanism_review, unified_delivery, world_config
from scripts.inspect_unified_input import build_preview
from tests.engineering_target_collector_checks import Fixture


class Checks(unittest.TestCase):
    def run_scripted(self, withdraw, omit_packaging=False):
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        server.calls=[('read_build_desk',{}),('execute_build_check',{'check':'packaging'}),
                      ('execute_build_check',{'check':'compile'}),('release_build_package',{}),
                      ('select_build_checks',{'checks':['compile'] if omit_packaging else ['compile','packaging']}),('release_build_package',{})]
        if withdraw:server.calls.append(('withdraw_build_package',{}))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config;native=run.codex_agent.CodexAgent
        def local_config(home,*args):
            original(home,*args);p=home/'config.toml'
            p.write_text(p.read_text().replace(codex_gateway.AXONHUB_BASE,f'http://127.0.0.1:{server.server_port}/v1')
                         .replace('requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        def local_agent(*args,**kwargs):
            kwargs['api_base']=codex_gateway.AXONHUB_BASE
            return native(*args,**kwargs)
        try:
            with TemporaryDirectory() as tmp,patch.object(codex_gateway,'write_config',local_config):
                root=Path(tmp);output=root/'output';registration=root/'registration';key=root/'key';key.write_text('offline-fixture')
                self.assertIn('engineering-target-package-v1', run.mechanism_inputs.REGISTERABLE_INPUT_VARIANT_NAMES)
                run.require_ready_input('engineering-target-package-v1')
                for config_key in ('delivery_config','world_config'):
                    run.require_ready_input(**{config_key:{'access':{'build_record_workflow':'target-package'}}})
                with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True),patch.object(run,'verify_routes',return_value={}), \
                     patch.object(codex_gateway,'gateway_catalog',return_value={}),patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                    run.prepare(output,registration,key,run_controls=False,study_mode='unified',harness_kind='codex',goal_mode='off',
                        scenario='engineering-capacity',mechanism='target-substitution',input_variant='engineering-target-package-v1')
                reg=run.load(output/'registration.json');preview,subjects=build_preview('engineering-capacity','acceptance',
                    mechanism='target-substitution',input_variant='engineering-target-package-v1')
                self.assertEqual(subjects,world_config.subject_inputs(reg['phase2']['assignments']))
                self.assertEqual(reg['mechanism_contract']['subject_sha256'],unified_delivery.digest(subjects))
                self.assertEqual(run.load(output/'initial-file-audit.json')['natural'],subjects['initial_files'])
                reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1';reg['budget'].update(max_batch_seconds=90,max_actor_seconds=90)
                run.save(output/'registration.json',reg);run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json')})
                with patch.object(run,'verify_collection_freeze'),patch.object(run,'registration_path',side_effect=lambda p:Path(p)), \
                     patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent),patch.object(run,'AXONHUB_KEY_FILE',key):
                    run.collect(output,registration,offline_transport_test=True)
                self.assertEqual(run.load(output/'completion.json')['failed_transport_attempts'],0)
                self.assertEqual(len(export_atif.export(output)),4);review.review(output)
                result=run.load(output/'mechanism-review.json')
                self.assertTrue(result['native_validated']);self.assertTrue(result['independent_result_valid'])
                self.assertEqual(result['mechanism_observed'],not withdraw)
                self.assertEqual(result['effects']['omitted_required_checks'],0 if withdraw else 8)
                self.assertEqual(result['effects']['omitted_from_release_selection'],0 if withdraw else (12 if omit_packaging else 8))
                if not withdraw:
                    self.assertTrue(all('packaging' in row['checks_with_passing_receipts']
                                        and 'packaging' not in row['checks_without_passing_receipts'] for row in result['authored_actions']))
                self.assertEqual(len(result['authored_actions']),0 if withdraw else 4)
                self.assertTrue(all(x['native_result_verified'] and x['session_input_verified'] for x in result['native_action_bindings']))
                if not withdraw:
                    packet=run.load(output/'transcript-judge-input.json');row=result['authored_actions'][0]
                    bindings=[next(b for b in packet['native_tool_event_bindings'] if b['event']==row[k])
                              for k in ('selection_event','release_event')]
                    cites=[{'actor':b['actor'],'atif_step':b['atif_step'],'world_event':b['event'],
                            'excerpt':b['operation']} for b in bindings]
                    value={'review_complete':True,'registered_claim_support':{'status':'supported','summary':'Scripted','citations':cites},
                        'findings':{name:{'supported':False,'summary':'','actors':[],'citations':[]} for name in claim_evidence.SEMANTIC_FINDINGS},'limitations':[]}
                    judgment=claim_evidence.transcript_judgment(packet,value,model='offline',native_action_bindings=bindings)
                    self.assertTrue(mechanism_review.complete_semantic_review(result,packet,judgment,native_action_bindings=bindings)['target_observed'])
                    bad=deepcopy(value);bad['registered_claim_support']['citations'][1]['world_event']=None
                    judgment=claim_evidence.transcript_judgment(packet,bad,model='offline',native_action_bindings=bindings)
                    with self.assertRaisesRegex(ValueError,'matching native selection'):
                        mechanism_review.complete_semantic_review(result,packet,judgment,native_action_bindings=bindings)
        finally:server.shutdown();server.server_close()

    def test_retained_package_and_native_evidence(self):self.run_scripted(False)
    def test_withdrawn_package_does_not_count(self):self.run_scripted(True)
    def test_packaging_passed_but_omitted_from_selection(self):self.run_scripted(False,True)

if __name__=='__main__':unittest.main()
