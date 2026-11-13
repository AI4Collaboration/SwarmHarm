"""Scripted local native transport; it provides no model-behavior evidence."""
from http.server import ThreadingHTTPServer
from datetime import datetime,timezone
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

import codex_gateway,export_atif,review,run
from phase2 import finance_closure, finance_recurring
from tests.unified_runtime_checks import DispatchFixture


class Fixture(DispatchFixture):
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        results=[row for row in request['input'] if row.get('type')=='function_call_output']
        step=len(results)
        if '"confirm_service"' in json.dumps(request.get('tools',[])):
            name,args=('confirm_service',{}) if step==0 else (None,None)
        elif step==0:name,args='read_payment_account',{}
        elif step==1:
            payload=results[0]['output']
            value=json.loads(payload) if isinstance(payload,str) else payload
            if isinstance(value,list):
                text=next(item['text'] for item in value if item.get('text','').lstrip().startswith('{'))
                value=json.loads(text)
            name,args='cancel_payment_order',{'invoice_id':value['invoice_id'],'account':'current'}
        elif step==2:name,args='close_payment_account',{}
        else:
            payload=results[0]['output'];value=json.loads(payload) if isinstance(payload,str) else payload
            if isinstance(value,list):value=json.loads(next(item['text'] for item in value if item.get('text','').lstrip().startswith('{')))
            activated=datetime.now(timezone.utc)>=datetime.fromisoformat(value['replacement_expected_at'])
            used=any(row.get('type')=='function_call' and row.get('name')=='reissue_payment_order' for row in request['input'])
            name,args=(('reissue_payment_order',{'invoice_id':value['invoice_id'],'account':'replacement'})
                       if activated and not used else (None,None))
        item=({'type':'function_call','name':name,'namespace':'mcp__work','call_id':f'fixture-{step}',
               'arguments':json.dumps(args)} if name else
              {'type':'message','id':'end','role':'assistant','phase':'final_answer',
               'content':[{'type':'output_text','text':'Fixture done.'}]})
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        events=[{'type':'response.created','response':{'id':f'fixture-{step}'}},
                {'type':'response.output_item.done','output_index':0,'item':item},
                {'type':'response.completed','response':{'id':f'fixture-{step}','status':'completed',
                  'model':'openai/gpt-6.1-sol','output':[item],
                  'usage':{'input_tokens':10,'output_tokens':3,'total_tokens':13}}}]
        for event in events:self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode());self.wfile.flush()


class Checks(unittest.TestCase):
    def run_collector(self, recurring=False):
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config;native=run.codex_agent.CodexAgent
        def local_config(home,*args):
            original(home,*args);path=home/'config.toml'
            path.write_text(path.read_text().replace(codex_gateway.AXONHUB_BASE,f'http://127.0.0.1:{server.server_port}/v1')
                .replace('requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        def local_agent(*args,**kwargs):
            kwargs['api_base']=codex_gateway.AXONHUB_BASE
            return native(*args,**kwargs)
        try:
            with TemporaryDirectory() as tmp,patch.object(codex_gateway,'write_config',local_config), \
                 patch.multiple(finance_closure,DEADLINE=2.0,FIRST_WINDOW=5.0,ACTIVATION=6.0,SECOND_WINDOW=10.0), \
                 patch.multiple(finance_recurring,INTERVAL=5.0,OBSERVATION_MIN=16.0):
                root=Path(tmp);output=root/'output';registration=root/'registration';key=root/'key';key.write_text('offline-fixture')
                with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True), \
                     patch.object(run,'verify_routes',return_value={}),patch.object(codex_gateway,'gateway_catalog',return_value={}), \
                     patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                    run.prepare(output,registration,key,run_controls=False,study_mode='unified',harness_kind='codex',goal_mode='off',
                                scenario='financial-analysis',mechanism='work-lifecycle',input_variant=('finance-account-retirement-recurring-v1' if recurring else 'finance-account-retirement-v1'))
                reg=run.load(output/'registration.json');reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1'
                reg['budget'].update(max_batch_seconds=90,max_actor_seconds=90)
                run.save(output/'registration.json',reg);run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json')})
                with patch.object(run,'verify_collection_freeze'),patch.object(run,'registration_path',side_effect=lambda p:Path(p)), \
                     patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent),patch.object(run,'AXONHUB_KEY_FILE',key):
                    run.collect(output,registration,offline_transport_test=True)
                completion=run.load(output/'completion.json')
                self.assertIn(completion['status'],('collected','collected_with_limits'))
                self.assertEqual(completion['failed_transport_attempts'],0)
                self.assertEqual(len(export_atif.export(output)),4)
                review.review(output)
                observed=run.load(output/'mechanism-review.json')
                self.assertTrue(observed['native_validated'])
                self.assertTrue(all(row['native_result_verified'] and row['session_input_verified']
                                    for row in observed['native_action_bindings']))
                self.assertEqual(len(observed['causal_actors']),4)
                self.assertEqual(observed['effects']['missed_first_window_payments'],4)
                outcome=run.load(output/'natural/operator/finance-closure-observation.json')['mechanical_observation']
                self.assertEqual(len(outcome['second_sent']),4)
                if recurring:
                    self.assertEqual(len(outcome['later_sent']),1)
                    self.assertGreaterEqual(outcome['observation_end_seconds'],16)
                self.assertFalse(observed['target_observed'])
                from phase2 import claim_evidence
                value={'review_complete':True,'registered_claim_support':{'status':'not_supported','summary':'Offline fixture','citations':[]},
                       'findings':{name:{'supported':False,'summary':'Offline fixture','actors':[],'citations':[]}
                                   for name in claim_evidence.SEMANTIC_FINDINGS},'limitations':[]}
                response={'model':'openai/gpt-6.1-sol','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
                fixture=root/'judge-response.json';fixture.write_text(json.dumps(response))
                subprocess.run([sys.executable,str(run.HERE/'scripts/judge_unified_transcript.py'),
                                '--output',str(output),'--response-file',str(fixture)],check=True,capture_output=True,text=True)
                self.assertFalse(run.load(output/'mechanism-verdict.json')['target_observed'])
        finally:server.shutdown();server.server_close()

    def test_native_payment_receipts_and_fixed_event_replay(self):
        self.run_collector()

    def test_recurring_native_payment_receipts_and_fixed_event_replay(self):
        self.run_collector(recurring=True)


if __name__=='__main__':unittest.main()
