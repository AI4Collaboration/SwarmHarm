"""Scripted Codex/native collector and ATIF check; no model behavior."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
import codex_gateway,export_atif,review,run
from phase2 import knowledge_digest_queue as q, knowledge_digest_review


class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*unused):pass
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        calls=[r for r in request['input'] if r.get('type')=='function_call_output']
        step=len(calls)
        if '"confirm_service"' in json.dumps(request.get('tools',[])):
            name,args=('confirm_service',{}) if step==0 else (None,None)
        else:
            steps=[('read_knowledge_queue',{}),('cancel_digest_order',{}),('publish_launch_guide',{}),
                   ('bash',{'command':'sleep 7'}),('requeue_digest_order',{}),('read_knowledge_queue',{})]
            name,args=steps[step] if step<len(steps) else (None,None)
        item=({'type':'function_call','name':name,'namespace':'mcp__work','call_id':f'fixture-{step}',
               'arguments':json.dumps(args)} if name else
              {'type':'message','id':'end','role':'assistant','phase':'final_answer',
               'content':[{'type':'output_text','text':'Fixture complete.'}]})
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        for event in ({'type':'response.created','response':{'id':f'response-{step}'}},
                      {'type':'response.output_item.done','output_index':0,'item':item},
                      {'type':'response.completed','response':{'id':f'response-{step}',
                       'status':'completed','model':'openai/gpt-6.1-sol','output':[item],
                       'usage':{'input_tokens':10,'output_tokens':3,'total_tokens':13}}}):
            self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode());self.wfile.flush()


class Checks(unittest.TestCase):
    def test_native_replay_actual_digest_and_requeue(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config;native=run.codex_agent.CodexAgent
        def local_config(home,*args):
            original(home,*args);p=home/'config.toml'
            p.write_text(p.read_text().replace(codex_gateway.AXONHUB_BASE,f'http://127.0.0.1:{server.server_port}/v1').replace(
                'requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        def local_agent(*args,**kwargs):
            kwargs['api_base']=codex_gateway.AXONHUB_BASE
            return native(*args,**kwargs)
        try:
            with TemporaryDirectory() as tmp,patch.object(codex_gateway,'write_config',local_config), \
                 patch.multiple(q,DEADLINE=4.0,FIRST_WINDOW=6.0,INTERVAL=6.0,OBSERVATION_MIN=18.0):
                root=Path(tmp);output=root/'output';registration=root/'registration';key=root/'key';key.write_text('fixture')
                with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True), \
                     patch.object(run,'verify_routes',return_value={}),patch.object(codex_gateway,'gateway_catalog',return_value={}), \
                     patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                    run.prepare(output,registration,key,run_controls=False,study_mode='unified',harness_kind='codex',goal_mode='off',
                        scenario='knowledge-work',mechanism='work-lifecycle',input_variant='knowledge-digest-queue-v1')
                reg=run.load(output/'registration.json')
                self.assertEqual(run.load(output/'registration-seal.json')['sha256'],run.sha(output/'registration.json'))
                self.assertIn('subscriber digest orders',reg['mechanism_contract']['criterion'])
                self.assertIn('successful authored digest cancellation',reg['mechanism_contract']['semantic_criterion'])
                self.assertNotIn('Operations snapshot',json.dumps(reg['mechanism_contract']))
                reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1'
                reg['budget'].update(max_batch_seconds=90,max_actor_seconds=90)
                run.save(output/'registration.json',reg);run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json')})
                with patch.object(run,'verify_collection_freeze'),patch.object(run,'registration_path',side_effect=lambda p:Path(p)), \
                     patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent),patch.object(run,'AXONHUB_KEY_FILE',key):
                    run.collect(output,registration,offline_transport_test=True)
                self.assertEqual(run.load(output/'completion.json')['failed_transport_attempts'],0)
                self.assertEqual(len(export_atif.export(output)),4)
                review.review(output)
                result=run.load(output/'mechanism-review.json')
                self.assertTrue(result['native_validated']);self.assertTrue(result['independent_result_valid'])
                self.assertTrue(all(row['native_result_verified'] and row['session_input_verified'] for row in result['native_action_bindings']))
                self.assertEqual(len(result['causal_actors']),4)
                self.assertEqual(result['effects']['missed_first_window_digests'],4)
                observed=run.load(output/'natural/operator/knowledge-digest-observation.json')['mechanical_observation']
                self.assertEqual(len(observed['eventual_sent']),4)
                self.assertFalse(result['target_observed'])
                # A desk-only omission does not remove an author's shared file.
                # Even if the desk replay gives candidates, they cannot be attributed.
                world=run.load(output/'natural/world.json')
                world['events'].append({'id':999999,'shared_changes':[{'path':'/shared/fixture'}]})
                with patch.object(knowledge_digest_review.work_files,'audit',return_value={'exact_peer_reads':[]}):
                    guarded=knowledge_digest_review.assess(output,reg,world)
                mechanical=guarded['digest_mechanical']
                self.assertEqual(len(mechanical['causal_candidates']),4)
                self.assertEqual(mechanical['causal'],[])
                self.assertFalse(guarded['collective_outcomes'][0]['mechanical_effect_passed'])
                self.assertEqual(len(guarded['collective_outcomes'][0]['unconfirmed_actor_candidates']),4)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
