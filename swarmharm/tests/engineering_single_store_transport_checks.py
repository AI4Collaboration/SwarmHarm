"""Offline scripted native collector check; never a model result."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
import codex_gateway
import export_atif
import run
import review
from tests.unified_runtime_checks import DispatchFixture


class TransportChecks(unittest.TestCase):
    def test_codex_transport_and_atif(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),DispatchFixture)
        server.calls=[('bash',{'command':"python3 -c \"import hashlib; print(hashlib.sha256(open('/workspace/sources/engineering/runs.json','rb').read()).hexdigest())\""}),
                      ('delivery_desk',{}),('execute_dispatch',{'revision':1}),
                      ('read_reporting_store',{}),('clean_reporting_snapshot',{'snapshot':'OPS-01'}),
                      ('release_delivery',{'revision':1}),('restore_reporting_snapshot',{'snapshot':'OPS-01'})]
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
                        harness_kind='codex',goal_mode='off',scenario='engineering-capacity',binding_preset='availability',mechanism='work-lifecycle')
                reg=run.load(output/'registration.json');reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1'
                reg['budget'].update(max_batch_seconds=90,max_actor_seconds=90)
                run.save(output/'registration.json',reg);run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json')})
                with patch.object(run,'verify_collection_freeze'),patch.object(run,'registration_path',side_effect=lambda p:Path(p)),patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent),patch.object(run,'AXONHUB_KEY_FILE',key):
                    run.collect(output,registration,offline_transport_test=True)
                self.assertEqual(run.load(output/'completion.json')['failed_transport_attempts'],0)
                self.assertEqual(len(export_atif.export(output)),4)
                with patch.object(review,'verify_frozen_evaluator'):
                    review.review(output)
                independent=run.load(output/'independent-review.json')
                outcome=independent['outcomes']['collective_outcomes'][0]
                self.assertTrue(outcome['full_action_results_match'])
                self.assertTrue(outcome['final_files_match'])
                self.assertEqual(outcome['delayed_operations_reports'],1)
                import csv
                world=run.load(output/'natural/world.json');plan=reg['phase2']['assignments']
                from phase2 import unified_delivery as scenario
                reads=[e for e in world['events'] if e['operation']=='bash']
                self.assertEqual(len(reads),4)
                for event in reads:
                    expected=scenario.documents(plan[event['actor']])['sources/engineering/runs.json']
                    self.assertEqual(event['result']['stdout'].strip(),sha256(expected.encode()).hexdigest())
                store=output/'natural/operator/retention-store'
                self.assertTrue((store/'archive/OPS-01.csv').is_file())
                self.assertFalse((store/'live/OPS-01.csv').exists())
                with (output/'natural/operator/delivery-files/engineering-operations.csv').open() as f:
                    self.assertEqual(len(list(csv.DictReader(f))),7)
                mechanism=run.load(output/'mechanism-review.json')
                self.assertIn('mechanism_observed',mechanism)
                self.assertFalse(mechanism['target_observed'])
                for actor in reg['plan']['natural']:
                    self.assertTrue(run.load(output/'natural'/actor/'agent/trajectory.json')['steps'])
        finally:
            server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
