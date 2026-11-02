"""Native SDK turn limits with local scripted inference, never hosted calls."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import shutil
from contextlib import ExitStack
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import run
import export_atif
from tests.claude_collect_checks import ScriptedMessages, MODEL

CLAUDE = run.claude_agent


class ToolLoopMessages(ScriptedMessages):
    requests = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append(body)
        tools = [t['name'] for t in body.get('tools',[]) if t['name'].startswith('mcp__')]
        number = len(type(self).requests)
        block = ({'type':'tool_use','id':f'toolu_{number}','name':tools[0],'input':{}} if tools
                 else {'type':'text','text':'{"title":"Local fixture"}'})
        initial = {**block,'input':{}} if tools else {'type':'text','text':''}
        delta = {'type':'input_json_delta','partial_json':'{}'} if tools else {'type':'text_delta','text':block['text']}
        message = {'id':f'msg_{number}','type':'message','role':'assistant','model':MODEL,
                   'content':[],'stop_reason':None,'stop_sequence':None,
                   'usage':{'input_tokens':10,'output_tokens':0}}
        frames = [{'type':'message_start','message':message},
                  {'type':'content_block_start','index':0,'content_block':initial},
                  {'type':'content_block_delta','index':0,'delta':delta},
                  {'type':'content_block_stop','index':0},
                  {'type':'message_delta','delta':{'stop_reason':'tool_use' if tools else 'end_turn','stop_sequence':None},'usage':{'output_tokens':5}},
                  {'type':'message_stop'}]
        self.send_response(200);self.send_header('Content-Type','text/event-stream')
        self.send_header('Connection','close');self.end_headers()
        for frame in frames:
            self.wfile.write(f"event: {frame['type']}\ndata: {json.dumps(frame)}\n\n".encode())


class ClaudeTurnLimitChecks(unittest.TestCase):
    def test_cap_survives_streamed_business_updates_without_replacing_native_goal(self):
        ScriptedMessages.requests = []
        server = ThreadingHTTPServer(('127.0.0.1', 0), ScriptedMessages)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)/'local-sdk.mjs'
            fixture.write_text(
                f'import * as sdk from {json.dumps((CLAUDE.CLAUDE_DIR/"node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs").as_uri())};\n'
                f'import {{serve}} from {json.dumps((CLAUDE.CLAUDE_DIR/"agent.mjs").as_uri())};\n'
                f'serve({{...sdk,query:(args)=>sdk.query({{...args,options:{{...args.options,env:{{...args.options.env,ANTHROPIC_API_KEY:"offline-fixture-key",ANTHROPIC_BASE_URL:"http://127.0.0.1:{server.server_port}"}}}}}})}});')
            clean = {k: os.environ[k] for k in ('PATH','HOME','USER','TMPDIR') if k in os.environ}
            clean.update(CLAUDE.RUNTIME_ENV)
            tool = {'name':'confirm_service','description':'Read service status.',
                    'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}
            events = CLAUDE.new_queue()
            with patch.object(CLAUDE,'AGENT',fixture), \
                    patch.object(CLAUDE,'subscription_env',return_value=clean), \
                    patch.object(CLAUDE,'SETTINGS',{**CLAUDE.SETTINGS,'maxTurns':3}):
                agent = CLAUDE.ClaudeAgent('cap',events,folder=Path(temporary)/'evidence',model=MODEL,
                    thinking_level='medium',max_output_tokens=1024,request_timeout_ms=10000,
                    tools=[tool],active_tools=['confirm_service'],job_context=None,goal_mode='off')
            try:
                CLAUDE.wait_ready(events,['cap'])
                agent.prompt('Check service status.')
                requests = []
                def until(expected):
                    while True:
                        _, message = events.get(timeout=30)
                        if message['type']=='request': requests.append(message)
                        elif message['type']=='tool_call': agent.reply(message['id'],output='{"status":"available"}')
                        elif message['type']==expected: return message
                        elif message['type'] in ('fatal','closed','exited'): self.fail(str(message))
                settled = until('settled')
                self.assertFalse(settled.get('error_message'))
                self.assertEqual(len(requests),2)
                agent.prompt('Business state changed. Check the new service status.')
                limit = until('budget_limit')
                self.assertEqual(limit['limit']['subject_turns'],3)
                self.assertEqual(limit['limit']['source'],'Stop')
                self.assertEqual(len(requests),3)
                count = sum(bool(row.get('tools')) for row in ScriptedMessages.requests)
                self.assertEqual(count,3)
                agent.prompt('A further platform update must not reopen the exhausted budget.')
                time.sleep(.2)
                self.assertEqual(sum(bool(row.get('tools')) for row in ScriptedMessages.requests),count)
                record = json.loads((Path(temporary)/'evidence/actor-turn-limit.json').read_text())
                self.assertEqual(record['scope'],'persistent_actor_session')
            finally:
                agent.close()

    def test_registered_limit_is_budget_not_provider_error(self):
        error = run.ActorTurnLimit('a',{'limit':25,'subject_turns':25})
        self.assertIsInstance(error,run.RolloutLimit)
        self.assertNotIsInstance(error,run.Hold)
        self.assertEqual(error.actor,'a')

    def test_common_collector_preserves_budget_terminal_cleanup_and_native_exports(self):
        ScriptedMessages.requests=[]
        server=ThreadingHTTPServer(('127.0.0.1',0),ScriptedMessages)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as patches:
            root=Path(temporary)/'study'
            registration=run.REGISTRATIONS/('test-turn-cap-'+Path(temporary).name)
            self.addCleanup(shutil.rmtree,registration,True)
            fixture=Path(temporary)/'local-collector.mjs'
            fixture.write_text(
                f'import * as sdk from {json.dumps((CLAUDE.CLAUDE_DIR/"node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs").as_uri())};\n'
                f'import {{serve}} from {json.dumps((CLAUDE.CLAUDE_DIR/"agent.mjs").as_uri())};\n'
                f'serve({{...sdk,query:(args)=>sdk.query({{...args,options:{{...args.options,env:{{...args.options.env,ANTHROPIC_API_KEY:"offline-fixture-key",ANTHROPIC_BASE_URL:"http://127.0.0.1:{server.server_port}"}}}}}})}});')
            clean={k:os.environ[k] for k in ('PATH','HOME','USER','TMPDIR') if k in os.environ}
            clean.update(CLAUDE.RUNTIME_ENV)
            patches.enter_context(patch.object(CLAUDE,'AGENT',fixture))
            patches.enter_context(patch.object(CLAUDE,'subscription_env',return_value=clean))
            patches.enter_context(patch.object(CLAUDE,'SETTINGS',{**CLAUDE.SETTINGS,'maxTurns':3}))
            patches.enter_context(patch.object(CLAUDE,'subscription_auth',return_value={'logged_in':True,'auth_method':'claude.ai','api_provider':'firstParty'}))
            patches.enter_context(patch.object(CLAUDE,'subscription_catalog',return_value={'model':MODEL,'effort':'medium','model_and_effort_found':True,'inference_calls':0}))
            patches.enter_context(patch.object(run,'MODELS',{'claude':MODEL}))
            patches.enter_context(patch.object(run,'UPSTREAM_MODELS',{'claude':MODEL}))
            run.prepare(root,registration,None,run_controls=False,harness_kind='claude-code',
                        reasoning_effort='medium',offline_adapter_test=True)
            reg=run.load(root/'registration.json')
            self.assertEqual(reg['per_agent_response_limit'],3)
            reg['budget'].update(max_actor_seconds=120,max_batch_seconds=120)
            reg['source_publication']['after_start_seconds']=1
            run.save(root/'registration.json',reg)
            run.save(root/'registration-seal.json',{'sha256':run.sha(root/'registration.json')})
            patches.enter_context(patch.object(run,'verify_collection_freeze'))
            patches.enter_context(patch.object(run,'AXONHUB_KEY_FILE',None))
            run.collect(root,registration,offline_adapter_test=True)
            completion=run.load(root/'completion.json')
            self.assertEqual(completion['status'],'rollout_limit',completion)
            self.assertEqual(completion['limit_kind'],'actor_turn_limit')
            self.assertNotEqual(completion['limited_actor'],'preflight')
            self.assertEqual(completion['turn_limit']['subject_turns'],3)
            self.assertTrue(run.load(root/'cleanup-summary.json')['model_calls_finished'])
            self.assertTrue(all(c['removed'] for c in run.load(root/'cleanup-summary.json')['owned_workstations']))
            exports=export_atif.export(root)
            self.assertEqual(len(exports),4)
            self.assertTrue(all(e['native_continuity_passed'] for e in exports))
            self.assertTrue(all(e['requests']<=3 for e in exports))

    def test_native_goal_tool_loop_hits_budget_without_an_extra_subject_request(self):
        ToolLoopMessages.requests = []
        server = ThreadingHTTPServer(('127.0.0.1',0),ToolLoopMessages)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)/'local-goal.mjs'
            fixture.write_text(
                f'import * as sdk from {json.dumps((CLAUDE.CLAUDE_DIR/"node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs").as_uri())};\n'
                f'import {{serve}} from {json.dumps((CLAUDE.CLAUDE_DIR/"agent.mjs").as_uri())};\n'
                f'serve({{...sdk,query:(args)=>sdk.query({{...args,options:{{...args.options,env:{{...args.options.env,ANTHROPIC_API_KEY:"offline-fixture-key",ANTHROPIC_BASE_URL:"http://127.0.0.1:{server.server_port}"}}}}}})}});')
            clean = {k:os.environ[k] for k in ('PATH','HOME','USER','TMPDIR') if k in os.environ}
            clean.update(CLAUDE.RUNTIME_ENV)
            tool = {'name':'confirm_service','description':'Read service status.',
                    'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}
            events = CLAUDE.new_queue();folder=Path(temporary)/'evidence'
            with patch.object(CLAUDE,'AGENT',fixture),patch.object(CLAUDE,'subscription_env',return_value=clean), \
                    patch.object(CLAUDE,'SETTINGS',{**CLAUDE.SETTINGS,'maxTurns':2}):
                agent = CLAUDE.ClaudeAgent('goal-cap',events,folder=folder,model=MODEL,
                    thinking_level='medium',max_output_tokens=1024,request_timeout_ms=10000,
                    tools=[tool],active_tools=['confirm_service'],job_context=None,goal_mode='claude_goal')
            try:
                ready=CLAUDE.wait_ready(events,['goal-cap'])['goal-cap']
                self.assertTrue(any(c['name']=='goal' for c in ready['commands']))
                agent.prompt('/goal Confirm service status.')
                requests=[]
                while True:
                    _,message=events.get(timeout=30)
                    if message['type']=='request':requests.append(message)
                    elif message['type']=='tool_call':agent.reply(message['id'],output='{"status":"available"}')
                    elif message['type']=='budget_limit':break
                    elif message['type'] in ('fatal','exited','closed'):self.fail(str(message))
                self.assertEqual(len(requests),2)
                self.assertEqual(message['limit']['subject_turns'],2)
                self.assertIn(message['limit']['source'],('PostToolBatch','sdk_max_turns'))
                time.sleep(.2)
                self.assertEqual(sum(bool(v.get('tools')) for v in ToolLoopMessages.requests),2)
                native=[json.loads(f.read_text()) for f in (folder/'native').glob('*.json')]
                self.assertEqual(sum(v.get('local_command_run',{}).get('command')=='goal' for v in native),1)
            finally:agent.close()


if __name__ == '__main__': unittest.main()
