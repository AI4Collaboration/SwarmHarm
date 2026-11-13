"""Production collector integration with scripted local transport; not behavioral evidence."""
from http.server import ThreadingHTTPServer
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
import codex_gateway,export_atif,review,run
from tests.unified_runtime_checks import DispatchFixture

class Fixture(DispatchFixture):
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        returned=sum(row.get('type')=='function_call_output' for row in request['input'])
        calls=self.server.calls
        if '"confirm_service"' in json.dumps(request.get('tools',[])):
            calls=[('confirm_service',{})]
        if returned>=len(calls):
            items=[{'type':'message','id':'end','role':'assistant','phase':'final_answer','content':[{'type':'output_text','text':'Fixture done.'}]}]
        else:
            name,args=calls[returned];items=[{'type':'function_call','name':name,'namespace':'mcp__work','call_id':f'fixture-{returned}','arguments':json.dumps(args)}]
            if name=='register_onboarding':
                from phase2.editorial_brief.editorial_desk import PARTNERS
                responses=[]
                for row in request['input']:
                    if row.get('type')!='function_call_output':continue
                    output=row.get('output')
                    chunks=[x.get('text','') for x in output] if isinstance(output,list) else [output]
                    for chunk in chunks:
                        if isinstance(chunk,str):
                            try:responses.append(json.loads(chunk))
                            except json.JSONDecodeError:pass
                account=next((row['account'] for row in responses if isinstance(row,dict) and 'account' in row and 'approved_topics' in row),None)
                if account is None:raise RuntimeError('No account in scripted status')
                items[0]['arguments']=json.dumps({'records':[{'partner':k,'sessions':v} for k,v in PARTNERS[account].items()]})
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        events=[{'type':'response.created','response':{'id':f'fixture-{returned}'}}]
        events.extend({'type':'response.output_item.done','output_index':i,'item':item} for i,item in enumerate(items))
        events.append({'type':'response.completed','response':{'id':f'fixture-{returned}','status':'completed','model':'openai/gpt-6.1-sol','output':items,'usage':{'input_tokens':10,'output_tokens':3,'total_tokens':13}}})
        for e in events:self.wfile.write(('event: '+e['type']+'\ndata: '+json.dumps(e)+'\n\n').encode());self.wfile.flush()

class Checks(unittest.TestCase):
    def run_collector(self, corrected, archive=False, publication_index=False, review_queue=False, review_context=False):
        review_queue = review_queue or review_context
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        server.calls=[('editorial_status',{}),('prepare_briefing',{'version':1}),('register_onboarding',{}),('select_topics',{'topics':['onboarding','renewal']}),('prepare_briefing',{'version':2}),('release_briefing',{'draft':'brief-1'}),('withdraw_briefing',{})]
        if review_queue:
            server.calls[3:4]=[('set_review_state',{'topic':'service','state':'cancelled'}),('set_review_state',{'topic':'support','state':'cancelled'}),('stage_review_queue',{})]
        if archive or publication_index or review_queue:server.calls[2:2]=[('list_intake_batches',{}),('read_intake_batch',{'partner':'Vela'})]
        if review_context:server.calls.insert(0,('read_review_queue',{}))
        if not corrected:server.calls.pop()
        if publication_index or review_queue:
            server.calls.insert(0,('list_published_briefings',{}))
            server.calls.append(('list_published_briefings',{}))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config;native=run.codex_agent.CodexAgent
        def local_config(home,*args):
            original(home,*args);p=home/'config.toml';p.write_text(p.read_text().replace(codex_gateway.AXONHUB_BASE,f'http://127.0.0.1:{server.server_port}/v1').replace('requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        def local_agent(*args,**kwargs):
            kwargs['api_base']=codex_gateway.AXONHUB_BASE
            return native(*args,**kwargs)
        try:
            with TemporaryDirectory() as tmp, patch.object(codex_gateway,'write_config',local_config):
                root=Path(tmp);output=root/'output';registration=root/'registration';key=root/'key';key.write_text('fixture')
                with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True),patch.object(run,'verify_routes',return_value={}),patch.object(codex_gateway,'gateway_catalog',return_value={}),patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                    variant='knowledge-review-context-v2' if review_context else 'knowledge-review-queue-v1' if review_queue else 'knowledge-publication-index-v1' if publication_index else 'knowledge-intake-archive-v1' if archive else None
                    run.prepare(output,registration,key,run_controls=False,study_mode='unified',harness_kind='codex',goal_mode='off',scenario='knowledge-work',mechanism='target-substitution',input_variant=variant)
                reg=run.load(output/'registration.json')
                from scripts.inspect_unified_input import build_preview
                from phase2 import world_config, unified_delivery
                if variant:
                    preview,subjects=build_preview('knowledge-work','acceptance',mechanism='target-substitution',input_variant=variant)
                    self.assertEqual(reg['mechanism_contract']['input_variant'],variant)
                else:
                    preview,subjects=build_preview('knowledge-work','acceptance',mechanism='target-substitution')
                self.assertEqual(preview['world_config'],reg['phase2']['assignments'][next(iter(reg['phase2']['assignments']))]['world_config'])
                self.assertEqual(subjects,world_config.subject_inputs(reg['phase2']['assignments']))
                self.assertEqual(reg['mechanism_contract']['subject_sha256'],unified_delivery.digest(subjects))
                audit=run.load(output/'initial-input-audit.json')['natural']
                for actor in reg['phase2']['assignments']:
                    self.assertEqual(audit[actor]['input'][0]['content'],subjects['tasks'][actor])
                    self.assertEqual(audit[actor]['tools'][1:],subjects['tools'])
                self.assertEqual(run.load(output/'initial-file-audit.json')['natural'],subjects['initial_files'])
                reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1';reg['budget'].update(max_batch_seconds=90,max_actor_seconds=90)
                run.save(output/'registration.json',reg);run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json')})
                with patch.object(run,'verify_collection_freeze'),patch.object(run,'registration_path',side_effect=lambda p:Path(p)),patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent),patch.object(run,'AXONHUB_KEY_FILE',key):
                    run.collect(output,registration,offline_transport_test=True)
                completion=run.load(output/'completion.json');self.assertIn(completion['status'],('collected','collected_with_limits'));self.assertEqual(completion['failed_transport_attempts'],0)
                self.assertEqual(len(export_atif.export(output)),4)
                review.review(output)
                result=run.load(output/'mechanism-review.json');self.assertFalse(result['target_observed'])
                self.assertEqual(result['mechanism_observed'],not corrected)
                self.assertEqual(len(result['causal_actors']),0 if corrected else 4)
                communication=run.load(output/'communication-evidence.json')
                self.assertEqual(communication['notes'],[])
                self.assertEqual(communication['exact_peer_reads'],[])
                if not corrected:
                    self.assertTrue(any(action['actor']!=action['selection_actor']
                                        for action in result['authored_actions']))
                # Scripted judgment is a software check only; no evidence of model behavior.
                from phase2 import claim_evidence
                value={'review_complete':True,'registered_claim_support':{'status':'not_supported','summary':'Offline fixture','citations':[]},
                    'findings':{name:{'supported':False,'summary':'Offline fixture','actors':[],'citations':[]}
                                for name in claim_evidence.SEMANTIC_FINDINGS},'limitations':[]}
                response={'model':'openai/gpt-6.1-sol','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
                fixture=root/'judge-response.json';fixture.write_text(json.dumps(response))
                subprocess.run([sys.executable,str(run.HERE/'scripts/judge_unified_transcript.py'),
                    '--output',str(output),'--response-file',str(fixture)],check=True,capture_output=True,text=True)
                verdict=run.load(output/'mechanism-verdict.json');self.assertFalse(verdict['target_observed'])

        finally:server.shutdown();server.server_close()

    def test_collector_retained_selection_needs_semantic_review(self):
        self.run_collector(False)

    def test_collector_correction_removes_retained_effect(self):
        self.run_collector(True)

    def test_archive_reads_are_native_business_inputs_not_agent_messages(self):
        self.run_collector(False,archive=True)

    def test_publication_index_uses_actual_releases_in_native_replay(self):
        self.run_collector(False,publication_index=True)

    def test_review_queue_native_collection_and_replay(self):
        self.run_collector(False, review_queue=True)

    def test_review_context_native_collection_and_replay(self):
        self.run_collector(False, review_context=True)
