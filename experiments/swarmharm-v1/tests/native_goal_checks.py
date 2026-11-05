"""Exercise real Codex goal continuation against a local scripted provider."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import patch
import codex_gateway
import run
import export_atif


class GoalResponses(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.captures.append(request)
        index=len(self.server.captures)
        if getattr(self.server, 'repeat_tool', False) and index % 2:
            items=[{'type':'function_call','namespace':'mcp__work','name':'confirm_service',
                    'call_id':f'call-{index}','arguments':'{}'}]
        elif getattr(self.server, 'text_only', False):
            items=[{'type':'message','id':f'msg-{index}','role':'assistant','phase':'final_answer',
                    'content':[{'type':'output_text','text':'Waiting for the service update.'}]}]
        elif index in (1,3):
            items=[{'type':'function_call','namespace':'mcp__work','name':'confirm_service',
                    'call_id':f'call-{index}','arguments':json.dumps({'after_reference':None,'channel':'public','limit':100})}]
        elif index==4:
            items=[{'type':'function_call','name':'update_goal','call_id':'goal-done',
                    'arguments':json.dumps({'status':self.server.terminal_status})}]
        else:
            items=[{'type':'message','id':f'msg-{index}','role':'assistant','phase':'final_answer',
                    'content':[{'type':'output_text','text':'First inspection finished; verify the next result.' if index==2 else 'Verified.'}]}]
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        events=[{'type':'response.created','response':{'id':f'resp-{index}'}}]
        events += [{'type':'response.output_item.done','output_index':i,'item':item} for i,item in enumerate(items)]
        events += [{'type':'response.completed','response':{'id':f'resp-{index}','status':'completed',
                   'model':request['model'],'output':items,'usage':{'input_tokens':10,'output_tokens':3,'total_tokens':13}}}]
        for event in events:
            self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode());self.wfile.flush()


class NativeGoalChecks(unittest.TestCase):
    def test_preparation_registers_codex_goal_without_pi_resume_contract(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);key=root/'key';key.write_text('offline-fixture')
            with patch.object(run,'REGISTRATIONS',root/'registrations'), \
                 patch.object(run,'MODELS',{'sol':'openai/gpt-5.6-sol'}), \
                 patch.object(run,'UPSTREAM_MODELS',{'sol':'openai/gpt-5.6-sol'}), \
                 patch.object(run,'verify_routes',return_value={}):
                run.prepare(root/'output',root/'registrations'/'goal',key,run_controls=False,
                    scenario='knowledge-work',study_mode='phase2-component',
                    component_family='trace-integrity',harness_kind='codex',goal_mode='codex_goal')
            registration=run.load(root/'output/registration.json')
            self.assertEqual(registration['native_subject_goal']['condition'],'native_codex_goal')
            self.assertNotIn('blocked_business_resumption',registration['native_subject_goal'])
            self.assertNotIn('subject_prompt_condition',registration)
            self.assertEqual(registration['native_subject_goal']['settings']['goal_progress_guard'],
                             codex_gateway.GOAL_PROGRESS_GUARD)
            stale_harness = dict(registration['harness'])
            stale_harness.pop('goal_progress_guard')
            with self.assertRaisesRegex(RuntimeError, 'goal guard changed'):
                codex_gateway.verify_runtime(stale_harness)
            self.assertNotIn('goals',registration['harness']['disabled_features'])
            self.assertIn('update_goal',registration['harness']['extension_tools'])
            self.assertNotIn('goal off',' '.join(registration['reproduction']['harness_differences']))

    def test_native_goal_continues_one_thread_and_exports_exact_evidence(self):
        self.exercise('complete')

    def test_blocked_native_goal_settles_without_controller_retry(self):
        self.exercise('blocked')

    def test_full_workstation_output_survives_native_goal_history(self):
        self.exercise('complete', large_output=True)

    def test_tool_free_continuation_stops_and_new_state_resumes_same_goal(self):
        self.exercise_guard()

    def test_repeated_identical_tool_results_do_not_reset_guard(self):
        self.exercise_guard(repeat_tool=True)

    def exercise_guard(self,repeat_tool=False):
        server=ThreadingHTTPServer(('127.0.0.1',0),GoalResponses)
        server.captures=[];server.text_only=True;server.repeat_tool=repeat_tool
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config
        def local_config(home,*args):
            original(home,*args)
            path=home/'config.toml'
            value=path.read_text().replace(codex_gateway.AXONHUB_BASE,f'http://127.0.0.1:{server.server_port}/v1')
            path.write_text(value.replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        try:
            with tempfile.TemporaryDirectory() as d,patch.object(codex_gateway,'write_config',local_config):
                folder=Path(d);events=queue.Queue();model='openai/gpt-5.6-sol'
                agent=run.codex_agent.CodexAgent('actor',events,folder=folder,model=model,
                    thinking_level='high',tools=[{'type':'function','name':'confirm_service',
                        'description':'Read service status.','parameters':{'type':'object','properties':{}}}],
                    active_tools=['confirm_service'],goal_mode='codex_goal',
                    api_base=codex_gateway.AXONHUB_BASE,api_key='offline-fixture',
                    registered_harness=codex_gateway.harness_registration('codex_goal',model))
                try:
                    run.codex_agent.wait_ready(events,['actor'])
                    for text in ('Verify the service result.', 'Service revision 2 is now available.'):
                        start_count=len(server.captures)
                        agent.prompt(text)
                        settlements=[]
                        while True:
                            try:
                                _,message=events.get(timeout=2 if settlements and settlements[-1]['native_goal']['goal']['status']=='paused' else 30)
                            except queue.Empty:
                                break
                            self.assertNotIn(message['type'],('fatal','exited'))
                            if message['type']=='tool_call':
                                agent.reply(message['id'],output='Service revision 1 unchanged.')
                            if message['type']=='settled':settlements.append(message)
                            self.assertLessEqual(len(server.captures)-start_count,8 if repeat_tool else 3,'Unbounded unchanged continuation')
                        self.assertIn(len(server.captures)-start_count,(4,6,8) if repeat_tool else (2,3))
                        self.assertTrue(settlements)
                        self.assertEqual(settlements[-1]['native_goal']['goal']['status'],'paused')
                        self.assertEqual(settlements[-1]['native_goal']['goal']['objective'],'Verify the service result.')
                        self.assertTrue(settlements[-1]['sdk_idle'])
                finally:
                    agent.close()
                    import shutil
                    diag=Path(tempfile.gettempdir())/f'swarmharm-codex-no-progress-{os.getpid()}'
                    if diag.exists():shutil.rmtree(diag)
                    shutil.copytree(folder,diag)
                    (diag/'outbound.json').write_text(json.dumps(server.captures,indent=2))
                raw=[json.loads(path.read_text())['message'] for path in (folder/'native').glob('*.json')]
                self.assertEqual(sum(m.get('method')=='thread/goal/set' and 'objective' in m['params'] for m in raw),1)
                self.assertEqual(sum(m.get('method')=='turn/start' for m in raw),2)
        finally:server.shutdown();server.server_close()

    def exercise(self,terminal_status,large_output=False):
        server=ThreadingHTTPServer(('127.0.0.1',0),GoalResponses);server.captures=[];server.terminal_status=terminal_status
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config
        def local_config(home,*args):
            original(home,*args)
            p=home/'config.toml';s=p.read_text().replace(codex_gateway.AXONHUB_BASE,f'http://127.0.0.1:{server.server_port}/v1')
            s=s.replace('requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0');p.write_text(s)
        try:
            with tempfile.TemporaryDirectory() as d,patch.object(codex_gateway,'write_config',local_config):
                root=Path(d);folder=root/'natural/actor';folder.mkdir(parents=True)
                events=queue.Queue();model='openai/gpt-5.6-sol'
                harness=codex_gateway.harness_registration('codex_goal',model)
                tools=[{'type':'function','name':'confirm_service','description':'Read service status.',
                        'parameters':{'type':'object','properties':{'after_reference':{'type':['string','null']},'channel':{'type':'string'},'limit':{'type':'integer'}},'required':['after_reference','channel','limit']}}]
                agent=run.codex_agent.CodexAgent('actor',events,folder=folder/'codex',model=model,
                    thinking_level='high',tools=tools,active_tools=['confirm_service'],goal_mode='codex_goal',
                    api_base=codex_gateway.AXONHUB_BASE,api_key='offline-fixture',registered_harness=harness)
                settlements=[];goals=[];tools_seen=0
                try:
                    ready=run.codex_agent.wait_ready(events,['actor'])['actor']
                    agent.prompt('Verify the service result.')
                    while True:
                        _,message=events.get(timeout=30);kind=message['type'];turn=message.get('turn',0)
                        trace=folder/'trace';trace.mkdir(exist_ok=True)
                        if kind=='request':run.save(trace/f'{turn:04d}.request.json',message['payload'])
                        elif kind in ('response_update','provider_response'):
                            value=message['response'] if kind=='response_update' else message['event']['response']
                            run.save(trace/f'{turn:04d}.response.json',value);run.save(folder/'history.json',message['history'])
                        elif kind=='tool_call':
                            tools_seen+=1;value={'status':'available','inspection':tools_seen}
                            if large_output:
                                value.update(stdout=('\"\n'*32000),stderr=('\"\n'*32000),output_truncated=False)
                            run.save(trace/f'{turn:04d}-tool-1.json',{'call_id':message['call_id'],'name':message['name'],
                                'arguments':json.dumps(message['arguments']),'event_id':tools_seen,'result':value})
                            agent.reply(message['id'],output=json.dumps(value))
                        elif kind=='native_goal_state':goals.append(message['native_goal'])
                        elif kind=='settled':
                            settlements.append(message)
                            if message['native_goal']['goal']['status']==terminal_status and message['sdk_idle']:break
                        elif kind in ('fatal','exited'):self.fail(str(message))
                        self.assertLess(len(server.captures),8,'Native goal did not terminate')
                finally:
                    agent.close()
                    # Keep a diagnostic copy outside the repo on fixture failures too.
                    import shutil
                    diag=Path(tempfile.gettempdir())/f'swarmharm-native-goal-fixture-{os.getpid()}'
                    if diag.exists():shutil.rmtree(diag)
                    shutil.copytree(root,diag)
                    (diag/'outbound.json').write_text(json.dumps(server.captures,indent=2))
                self.assertEqual(tools_seen,2)
                if large_output:
                    outputs=[entry for entry in server.captures[-1]['input'] if entry.get('type')=='function_call_output']
                    self.assertGreater(len(json.dumps(outputs)),250000)
                    self.assertNotIn('tokens truncated',json.dumps(outputs))
                for request in server.captures:
                    advertised={t['name'] for t in request['tools'] if t['type']=='function'}
                    self.assertEqual(advertised,set(codex_gateway.native_tools('codex_goal')))
                self.assertEqual(settlements[-1]['native_goal']['goal']['objective'],'Verify the service result.')
                self.assertTrue(any(s['native_goal']['goal']['status']=='active' for s in settlements))
                self.assertTrue(any(g['goal']['status']==terminal_status for g in goals))
                run.save(root/'registration.json',{'harness':harness})
                run.save(folder/'result.json',{'status':'collected','codex_session':ready})
                result=export_atif.export_actor(root,'natural','actor')
                self.assertTrue(result['native_continuity_passed']);self.assertEqual(result['tool_results'],2)
                raw=[json.loads(p.read_text())['message'] for p in (folder/'codex/native').glob('*.json')]
                self.assertEqual(sum(m.get('method')=='turn/start' for m in raw),1)
                self.assertEqual(sum(m.get('method')=='thread/goal/set' for m in raw),1)
                self.assertGreaterEqual(sum(m.get('method')=='turn/started' for m in raw),2)
        finally:server.shutdown();server.server_close()
