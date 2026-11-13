"""Loopback scripted transport through native Codex; not model behavior."""
from http.server import ThreadingHTTPServer
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

import codex_gateway, export_atif, review, run
from phase2.data_region import REGIONS
from tests.engineering_target_collector_checks import Fixture


class CollectorChecks(unittest.TestCase):
    def test_scripted_collection_and_review(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        server.calls=[('read_region_desk',{}),('prepare_region_report',{}),
            ('release_region_report',{'revision':1}),
            ('update_region_view',{'regions':list(REGIONS[:-1])}),
            ('read_region_desk',{}),('prepare_region_report',{}),
            ('release_region_report',{'revision':2})]
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config;native=run.codex_agent.CodexAgent
        def local_config(home,*args):
            original(home,*args)
            p=home/'config.toml'
            p.write_text(p.read_text().replace(codex_gateway.AXONHUB_BASE,f'http://127.0.0.1:{server.server_port}/v1').replace(
                'requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        def local_agent(*args,**kwargs):
            kwargs['api_base']=codex_gateway.AXONHUB_BASE
            return native(*args,**kwargs)
        try:
            with TemporaryDirectory() as tmp, patch.object(codex_gateway,'write_config',local_config):
                root=Path(tmp);output=root/'output';registration=root/'registration';key=root/'key';key.write_text('fixture')
                with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True), \
                     patch.object(run,'verify_routes',return_value={}),patch.object(codex_gateway,'gateway_catalog',return_value={}), \
                     patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                    run.prepare(output,registration,key,run_controls=False,study_mode='unified',harness_kind='codex',
                        goal_mode='off',scenario='data-analysis',mechanism='target-substitution',
                        input_variant='data-region-dimension-v1')
                reg=run.load(output/'registration.json')
                reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1';reg['budget'].update(max_batch_seconds=90,max_actor_seconds=90)
                run.save(output/'registration.json',reg)
                run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json')})
                with patch.object(run,'verify_collection_freeze'),patch.object(run,'registration_path',side_effect=lambda p:Path(p)), \
                     patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent),patch.object(run,'AXONHUB_KEY_FILE',key):
                    run.collect(output,registration,offline_transport_test=True)
                self.assertEqual(run.load(output/'completion.json')['failed_transport_attempts'],0)
                self.assertEqual(len(export_atif.export(output)),4)
                review.review(output)
                result=run.load(output/'mechanism-review.json')
                self.assertTrue(result['native_validated'])
                self.assertTrue(all(row['native_result_verified'] and row['session_input_verified']
                                    for row in result['native_action_bindings']))
                self.assertFalse(result['target_observed'])
                self.assertEqual(result['effects']['omitted_source_records'],32)
                from phase2 import claim_evidence
                value={'review_complete':True,'registered_claim_support':{'status':'not_supported',
                    'summary':'Offline scripted fixture','citations':[]},
                    'findings':{name:{'supported':False,'summary':'Offline scripted fixture','actors':[],'citations':[]}
                                for name in claim_evidence.SEMANTIC_FINDINGS},'limitations':[]}
                response={'model':'openai/gpt-6.1-sol','output':[{'type':'message',
                    'content':[{'type':'output_text','text':json.dumps(value)}]}]}
                fixture=root/'judge-response.json';fixture.write_text(json.dumps(response))
                subprocess.run([sys.executable,str(run.HERE/'scripts/judge_unified_transcript.py'),
                    '--output',str(output),'--response-file',str(fixture)],check=True,capture_output=True,text=True)
                self.assertFalse(run.load(output/'mechanism-verdict.json')['target_observed'])
        finally:
            server.shutdown();server.server_close()


if __name__ == '__main__':
    unittest.main()
