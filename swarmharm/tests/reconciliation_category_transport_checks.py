"""Scripted local transport; not a model behavior result."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
import codex_gateway
import export_atif
import run
import review
from tests.unified_runtime_checks import DispatchFixture


class CategoryTransportChecks(unittest.TestCase):
    def test_native_collection_and_independent_replay(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),DispatchFixture)
        server.calls=[('reconciliation_desk',{}),
            ('select_reconciliation_categories',{'categories':['receipts','payments']}),
            ('reconciliation_desk',{}),('prepare_reconciliation',{}),('release_reconciliation',{'revision':1})]
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config;native=run.codex_agent.CodexAgent
        def local_agent(*args,**kwargs):
            kwargs['api_base']=codex_gateway.AXONHUB_BASE
            return native(*args,**kwargs)
        def local_config(home,*args):
            original(home,*args);path=home/'config.toml'
            path.write_text(path.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1').replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        try:
            with TemporaryDirectory() as directory, patch.object(codex_gateway,'write_config',local_config), patch.object(run,'MODELS',{'sol':'openai/gpt-6.1-sol'}):
                root=Path(directory);output=root/'output';registration=root/'registration';key=root/'key';key.write_text('offline-fixture')
                with patch.object(run,'verify_routes',return_value={}),patch.object(codex_gateway,'gateway_catalog',return_value={}),patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                    run.prepare(output,registration,key,run_controls=False,study_mode='unified',
                        harness_kind='codex',goal_mode='off',scenario='financial-analysis',mechanism='target-substitution',input_variant='finance-category-template-v1')
                reg=run.load(output/'registration.json');reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1'
                reg['budget'].update(max_batch_seconds=90,max_actor_seconds=90)
                run.save(output/'registration.json',reg);run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json')})
                with patch.object(run,'verify_collection_freeze'),patch.object(run,'registration_path',side_effect=lambda p:Path(p)),patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent),patch.object(run,'AXONHUB_KEY_FILE',key):
                    run.collect(output,registration,offline_transport_test=True)
                self.assertEqual(run.load(output/'completion.json')['failed_transport_attempts'],0)
                self.assertEqual(len(export_atif.export(output)),4)
                with patch.object(review,'verify_frozen_evaluator'):review.review(output)
                effect=run.load(output/'independent-review.json')['outcomes']['collective_outcomes'][0]
                self.assertTrue(effect['full_action_results_match']);self.assertTrue(effect['final_files_match'])
                self.assertEqual(effect['omitted_source_records'],8)
                observed=run.load(output/'mechanism-review.json')
                self.assertTrue(observed['mechanism_observed'],observed)
                self.assertFalse(observed['target_observed'])
                self.assertEqual(observed['semantic_status'],'pending')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
