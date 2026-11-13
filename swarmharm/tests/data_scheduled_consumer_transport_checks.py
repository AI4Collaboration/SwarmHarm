"""Offline native Codex/ATIF/review wiring for scheduled Data consumers."""
from http.server import ThreadingHTTPServer
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import codex_gateway, export_atif, review, run
from phase2 import engineering_consumer, unified_delivery as scenario
from tests.data_partition_transport_checks import Fixture

class DataScheduledTransportChecks(unittest.TestCase):
    def test_scripted_native_to_independent_review(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        server.accounts=scenario.ACCOUNTS;server.calls={}
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config;native=run.codex_agent.CodexAgent
        def local_config(home,*args):
            original(home,*args);path=home/'config.toml'
            path.write_text(path.read_text().replace(codex_gateway.AXONHUB_BASE,f'http://127.0.0.1:{server.server_port}/v1').replace('requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        def local_agent(*args,**kwargs):
            kwargs['api_base']=codex_gateway.AXONHUB_BASE
            return native(*args,**kwargs)
        try:
            with TemporaryDirectory() as tmp, patch.object(codex_gateway,'write_config',local_config), patch.multiple(engineering_consumer,CONSUMER_DELAY=12.0,DELIVERY_DEADLINE=9.0):
                root=Path(tmp);out=root/'out';regpath=root/'reg';key=root/'key';key.write_text('offline-fixture')
                with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True),patch.object(run,'verify_routes',return_value={}),patch.object(codex_gateway,'gateway_catalog',return_value={}),patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                    run.prepare(out,regpath,key,run_controls=False,study_mode='unified',harness_kind='codex',goal_mode='off',scenario='data-analysis',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
                reg=run.load(out/'registration.json');plan=reg['phase2']['assignments']
                worker=next(row for row in plan.values() if row['account']=='Northline')
                for account in server.accounts:server.calls[account]=[('read_reporting_store',{})]
                server.calls['Northline']=[('read_reporting_store',{}),('stage_dispatch',{'items':list(scenario.ITEMS),'pools':['Northline']*4,'source_revision':scenario.SOURCE_REVISION}),*[('submit_report',{'item':item,'source_revision':scenario.SOURCE_REVISION,'csv':scenario.payload(worker,item)}) for item in scenario.ITEMS],('execute_dispatch',{'revision':6}),('clean_reporting_snapshot',{'snapshot':'OPS-01'}),('release_delivery',{'revision':6})]
                reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1';reg['budget'].update(max_batch_seconds=100,max_actor_seconds=100)
                run.save(out/'registration.json',reg);run.save(out/'registration-seal.json',{'sha256':run.sha(out/'registration.json')})
                with patch.object(run,'verify_collection_freeze'),patch.object(run,'registration_path',side_effect=lambda p:Path(p)),patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent),patch.object(run,'AXONHUB_KEY_FILE',key):
                    run.collect(out,regpath,offline_transport_test=True)
                self.assertEqual(run.load(out/'completion.json')['failed_transport_attempts'],0)
                self.assertEqual(len(export_atif.export(out)),4)
                with patch.object(review,'verify_frozen_evaluator'):review.review(out)
                result=run.load(out/'mechanism-review.json')
                self.assertTrue(result['native_validated']);self.assertEqual(result['first_attempt_missing'],['OPS-01'])
                self.assertTrue(all(row['native_result_verified'] and row['session_input_verified'] for row in result['native_action_bindings']))
                self.assertFalse(result['mechanism_observed'])
        finally:
            server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
