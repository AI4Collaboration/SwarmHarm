"""Subscription guards and offline collection through the real Claude Agent SDK."""
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import export_atif
import launch
import run

CLAUDE = run.claude_agent
# A recognized ID lets Claude Code apply its real per-model effort settings;
# inference is still served entirely by the localhost protocol fixture below.
MODEL = 'claude-opus-5-5'


class SubscriptionChecks(unittest.TestCase):
    def test_native_export_keeps_tool_heartbeat_without_accepting_nested_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            native=folder/'claude/native';native.mkdir(parents=True)
            run.save(folder/'result.json',{'claude_session':{'session_id':'session-1'}})
            run.save(native/'000001.json',{'type':'tool_progress','session_id':'session-1',
                'tool_use_id':'call-1-heartbeat-0','parent_tool_use_id':'call-1',
                'tool_name':'mcp__work__bash','elapsed_time_seconds':30,'heartbeat':True})
            hashes,_=export_atif.claude_native_evidence(folder,[])
            self.assertIn('claude/native/000001.json',hashes)
            run.save(native/'000002.json',{'type':'stream_event','session_id':'session-1',
                'parent_tool_use_id':'call-1','event':{'type':'message_start'}})
            with self.assertRaisesRegex(AssertionError,'nested Claude context'):
                export_atif.claude_native_evidence(folder,[])

    def test_api_and_cloud_credentials_fail_closed_without_exposing_values(self):
        for name in CLAUDE.CONFLICTING_ENV:
            with self.subTest(name=name), patch.dict(os.environ, {name: 'secret-test-value'}, clear=True):
                with self.assertRaisesRegex(RuntimeError, name) as error:
                    CLAUDE.subscription_env()
                self.assertNotIn('secret-test-value', str(error.exception))

    def test_subscription_environment_drops_unregistered_settings(self):
        with patch.dict(os.environ, {'HOME': '/home/operator', 'PATH': '/bin',
                'CLAUDE_CODE_OAUTH_TOKEN': 'subscription-token', 'UNRELATED_SECRET': 'secret',
                'ANTHROPIC_DEFAULT_OPUS_MODEL': 'other-model'}, clear=True):
            env = CLAUDE.subscription_env()
        self.assertEqual(env['CLAUDE_CODE_OAUTH_TOKEN'], 'subscription-token')
        self.assertNotIn('UNRELATED_SECRET', env)
        self.assertNotIn('ANTHROPIC_DEFAULT_OPUS_MODEL', env)

    def test_only_subscription_authentication_is_accepted_and_account_data_is_not_saved(self):
        for method in ('api_key', 'api_key_helper', 'third_party', 'none', 'claude.ai', 'oauth_token'):
            result = subprocess.CompletedProcess([], 0, json.dumps({
                'loggedIn': True, 'authMethod': method, 'apiProvider': 'firstParty',
                'email': 'private@example.com', 'accessToken': 'private-token', 'subscriptionType': 'max'}))
            with patch.object(CLAUDE, 'claude_binary', return_value='/bin/claude'), \
                    patch.object(CLAUDE, 'subscription_env', return_value={}), \
                    patch.object(CLAUDE.subprocess, 'run', return_value=result):
                if method in ('claude.ai', 'oauth_token'):
                    saved = CLAUDE.subscription_auth()
                    self.assertNotIn('private', json.dumps(saved))
                else:
                    with self.assertRaises(RuntimeError):CLAUDE.subscription_auth()

    def test_aliases_and_goal_mode_are_rejected(self):
        for model in ('opus', 'sonnet', 'default', 'claude-opus', 'claude-sonnet-4-latest',
                      'anthropic/claude-opus-4-6', 'claude-'):
            with self.assertRaises(ValueError):CLAUDE.validate_model(model)
        CLAUDE.validate_model('claude-sonnet-4-6')
        with self.assertRaisesRegex(ValueError, 'pi-goal'):CLAUDE.harness_registration('goal_command')

    def test_native_goal_registration_pins_evaluator_and_disables_timer_retries(self):
        with patch.object(CLAUDE,'subscription_auth',return_value={}), \
                patch.object(CLAUDE,'installed_versions',return_value={}), \
                patch.object(CLAUDE,'node_version',return_value='v22.22.3'), \
                patch.object(CLAUDE,'cli_identity',return_value={}):
            registration=CLAUDE.harness_registration('claude_goal',MODEL)
        self.assertEqual(registration['goal_evaluator']['model'],MODEL)
        self.assertEqual(registration['environment']['ANTHROPIC_DEFAULT_HAIKU_MODEL'],MODEL)
        self.assertEqual(registration['environment']['CLAUDE_CODE_GOAL_CHECKIN_MINUTES'],'0')
        self.assertEqual(registration['goal_progress_guard'],CLAUDE.GOAL_PROGRESS_GUARD)
        stale = dict(registration);stale.pop('goal_progress_guard')
        with self.assertRaisesRegex(RuntimeError, 'Claude goal guard changed'):
            CLAUDE.verify_runtime(stale)
        self.assertEqual(registration['extension_tools'],[])
        self.assertEqual(registration['system_prompt'],CLAUDE.SYSTEM_PROMPT)
        self.assertIn('Do not ask the user',registration['system_prompt']['append'])

    def test_claude_launcher_needs_no_api_key(self):
        with patch.object(launch, 'collector_python', return_value='/python'):
            argv = launch.collector_command('/tmp/study', '/tmp/registration')
        self.assertNotIn('--key-file', argv)

class ScriptedMessages(BaseHTTPRequestHandler):
    large_output = False
    goal_verdicts = None
    """Local Anthropic protocol fixture. No requests leave localhost."""
    requests = []
    capture_lock = threading.Lock()

    def log_message(self, *args):pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.capture_lock:
            type(self).requests.append(body)
            number = len(type(self).requests)
        tools = [tool['name'] for tool in body.get('tools', []) if tool['name'].startswith('mcp__')]
        phase2 = 'mcp__continuation__read_service_calendar' in tools
        target = ('mcp__continuation__read_service_calendar' if phase2
                  else 'mcp__work__confirm_service' if tools == ['mcp__work__confirm_service']
                  else 'mcp__work__bash')
        already = any(message.get('role') == 'assistant' and isinstance(message.get('content'), list)
                      and any(block.get('name') == target for block in message['content'])
                      for message in body['messages'])
        system='\n'.join(block.get('text','') for block in body.get('system',[]))
        if 'evaluating a stop-condition hook' in system and type(self).goal_verdicts is not None:
            verdict = type(self).goal_verdicts.pop(0)
            block={'type':'text','text':json.dumps(verdict)}
            initial={'type':'text','text':''}
            delta={'type':'text_delta','text':block['text']}
            reason='end_turn'
        elif 'naming a coding session' in system:
            block={'type':'text','text':'{"title":"Service status"}'}
            initial={'type':'text','text':''}
            delta={'type':'text_delta','text':block['text']}
            reason='end_turn'
        elif not already:
            block = {'type': 'tool_use', 'id': f'toolu_{number}', 'name': target, 'input': {}}
            if target.endswith('__bash'):
                cwd = re.search(r'/(?:private/)?tmp/workspace-[A-Za-z0-9]+', json.dumps(body))
                block['input'] = {'command': f'cd {cwd.group()} && ls' if cwd else 'ls /workspace'}
                if type(self).large_output:
                    block['input']['command'] += " && python3 -c \"print('x'*60000)\""
            delta = {'type': 'input_json_delta', 'partial_json': json.dumps(block['input'])}
            initial = {**block, 'input': {}}
            reason = 'tool_use'
        else:
            block = {'type': 'text', 'text': 'The workspace is listed.'}
            initial = {'type': 'text', 'text': ''}
            delta = {'type': 'text_delta', 'text': block['text']}
            reason = 'end_turn'
        message = {'id': f'msg_{number}', 'type': 'message', 'role': 'assistant',
                   'model': MODEL, 'content': [], 'stop_reason': None, 'stop_sequence': None,
                   'usage': {'input_tokens': 10, 'output_tokens': 0}}
        events = [
            {'type': 'message_start', 'message': message},
            {'type': 'content_block_start', 'index': 0, 'content_block': initial},
            {'type': 'content_block_delta', 'index': 0, 'delta': delta},
            {'type': 'content_block_stop', 'index': 0},
            {'type': 'message_delta', 'delta': {'stop_reason': reason, 'stop_sequence': None},
             'usage': {'output_tokens': 5}},
            {'type': 'message_stop'},
        ]
        if block['type']=='tool_use' and target.endswith('__bash') and not already:
            # Exercise two tool-use blocks in one real SDK response. The
            # controller must run both sequentially and bind both SDK echoes.
            events[4:4] = [
                {'type': 'content_block_start', 'index': 1, 'content_block': {
                    'type': 'tool_use', 'id': f'toolu_{number}_second', 'name': target, 'input': {}}},
                {'type': 'content_block_delta', 'index': 1, 'delta': {
                    'type': 'input_json_delta', 'partial_json': '{"command":"pwd"}'}},
                {'type': 'content_block_stop', 'index': 1},
            ]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Connection', 'close')
        self.end_headers()
        for event in events:
            self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())


@unittest.skipUnless((shutil.which('node') or os.environ.get('SWARMHARM_NODE'))
    and (CLAUDE.CLAUDE_DIR / 'node_modules/.bin/claude').exists()
    and (CLAUDE.CLAUDE_DIR / 'node_modules/@anthropic-ai/claude-agent-sdk/package.json').exists(),
    'Install the repository-local Claude runtime and Node.js')
class ClaudeCollectChecks(unittest.TestCase):
    def test_real_sdk_native_goal_is_acknowledged_before_first_model_request(self):
        ScriptedMessages.requests=[]
        server=ThreadingHTTPServer(('127.0.0.1',0),ScriptedMessages)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temporary:
            fixture=Path(temporary)/'offline-goal.mjs'
            fixture.write_text(
                f'import * as sdk from {json.dumps((CLAUDE.CLAUDE_DIR / "node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs").as_uri())};\n'
                f'import {{serve}} from {json.dumps((CLAUDE.CLAUDE_DIR / "agent.mjs").as_uri())};\n'
                f'serve({{...sdk, query: (args) => sdk.query({{...args, options: {{...args.options, env: {{...args.options.env, '
                f'ANTHROPIC_API_KEY: "offline-fixture-key", ANTHROPIC_BASE_URL: "http://127.0.0.1:{server.server_port}"}}}}}})}});\n')
            clean_env={name:os.environ[name] for name in ('PATH','HOME','USER','TMPDIR') if name in os.environ}
            clean_env.update(CLAUDE.RUNTIME_ENV)
            tool={'name':'confirm_service','description':'Read the service status.',
                  'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}
            events=CLAUDE.new_queue()
            with patch.object(CLAUDE,'AGENT',fixture),patch.object(CLAUDE,'subscription_env',return_value=clean_env):
                agent=CLAUDE.ClaudeAgent('goal',events,folder=Path(temporary)/'goal',model=MODEL,
                    thinking_level='medium',max_output_tokens=1024,request_timeout_ms=10000,
                    tools=[tool],active_tools=['confirm_service'],
                    job_context='{"job_id":"operator-bookkeeping-only"}',goal_mode='claude_goal')
            try:
                ready=CLAUDE.wait_ready(events,['goal'])['goal']
                self.assertTrue(any(command['name']=='goal' for command in ready['commands']))
                agent.prompt('/goal The service status is confirmed.')
                _,event=events.get(timeout=30)
                while event['type']=='native_goal_state':_,event=events.get(timeout=30)
                self.assertEqual(event['type'],'request',event)
                self.assertEqual(event['payload']['reasoning']['effort'],'medium')
                self.assertEqual(event['payload']['system_prompt_config'],CLAUDE.SYSTEM_PROMPT)
                native=[run.load(path) for path in (Path(temporary)/'goal/native').glob('*.json')]
                confirmations=[message for message in native if message.get('local_command_run',{}).get('command')=='goal']
                self.assertEqual(len(confirmations),1)
                self.assertEqual(confirmations[0]['local_command_run']['args'],'The service status is confirmed.')
                subject_requests=[value for value in ScriptedMessages.requests if value.get('tools')]
                self.assertTrue(subject_requests)
                self.assertEqual(subject_requests[0]['model'],MODEL)
                prompt='\n'.join(block.get('text','') for block in subject_requests[0]['system'])
                self.assertIn('permission',prompt.lower())
                self.assertIn('authorized security testing',prompt)
                self.assertNotIn('You help the user complete their work by reading files',prompt)
                self.assertNotIn('operator-bookkeeping-only',json.dumps(subject_requests))
            finally:agent.close()

    def test_gateway_native_goal_continues_then_settles_without_controller_nudges(self):
        ScriptedMessages.requests=[]
        ScriptedMessages.goal_verdicts=[
            {'ok':False,'reason':'Report the observed service status.'},
            {'ok':True,'reason':'Service result confirmed.'}]
        self.addCleanup(setattr,ScriptedMessages,'goal_verdicts',None)
        server=ThreadingHTTPServer(('127.0.0.1',0),ScriptedMessages)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/'goal'
            fixture=Path(temporary)/'gateway-goal.mjs'
            fixture.write_text(
                f'import * as sdk from {json.dumps((CLAUDE.CLAUDE_DIR / "node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs").as_uri())};\n'
                f'import {{serve}} from {json.dumps((CLAUDE.CLAUDE_DIR / "agent.mjs").as_uri())};\n'
                f'serve({{...sdk, query: args => sdk.query({{...args, options: {{...args.options, env: {{...args.options.env, '
                f'ANTHROPIC_API_KEY: "offline", ANTHROPIC_BASE_URL: "http://127.0.0.1:{server.server_port}"}}}}}})}});')
            env={k:os.environ[k] for k in ('PATH','HOME','USER','TMPDIR') if k in os.environ}
            env.update(CLAUDE.RUNTIME_ENV)
            model='anthropic/claude-opus-5.5'
            env['ANTHROPIC_DEFAULT_HAIKU_MODEL']=model
            tool={'name':'confirm_service','description':'Read the service status.',
                  'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}
            events=CLAUDE.new_queue();seen=[]
            with patch.object(CLAUDE,'AGENT',fixture),patch.object(CLAUDE,'gateway_env',return_value=env):
                agent=CLAUDE.ClaudeAgent('goal',events,folder=folder,model=model,thinking_level='medium',
                    max_output_tokens=1024,request_timeout_ms=10000,tools=[tool],active_tools=['confirm_service'],
                    goal_mode='claude_goal',api_base=CLAUDE.AXONHUB_BASE,api_key='offline')
            try:
                CLAUDE.wait_ready(events,['goal'])
                agent.prompt("Complete the user's task.",'/goal The service status is confirmed.')
                while True:
                    _,event=events.get(timeout=30);seen.append(event)
                    self.assertNotEqual(event['type'],'fatal',event)
                    if event['type']=='tool_call':agent.reply(event['id'],output='{"status":"confirmed"}')
                    if event['type']=='settled':
                        self.assertIsNone(event['error_message']);break
            finally:agent.close()
            requests=[e for e in seen if e['type']=='request']
            self.assertEqual(len(requests),3)
            self.assertIn('Stop hook feedback',json.dumps(requests[-1]['payload']['input']))
            goals=[e['native_goal']['value'] for e in seen if e['type']=='native_goal_state']
            self.assertTrue(goals[-1]['met']);self.assertEqual(goals[-1]['iterations'],2)
            native=[run.load(p) for p in (folder/'native').glob('*.json')]
            self.assertEqual(sum(e['type']=='controller_input' for e in native),1)
            self.assertEqual(len(ScriptedMessages.goal_verdicts),0)
            self.assertTrue(all(r['model']==model for r in ScriptedMessages.requests))
            self.assertEqual(sum('evaluating a stop-condition hook' in json.dumps(r.get('system'))
                                 for r in ScriptedMessages.requests),2)

    def test_native_goal_parks_no_progress_and_resumes_same_goal_on_new_state(self):
        ScriptedMessages.requests=[]
        ScriptedMessages.goal_verdicts=[{'ok':False,'reason':'The result remains pending.'} for _ in range(12)]
        self.addCleanup(setattr,ScriptedMessages,'goal_verdicts',None)
        server=ThreadingHTTPServer(('127.0.0.1',0),ScriptedMessages)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/'goal'
            fixture=Path(temporary)/'gateway-goal.mjs'
            fixture.write_text(
                f'import * as sdk from {json.dumps((CLAUDE.CLAUDE_DIR / "node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs").as_uri())};\n'
                f'import {{serve}} from {json.dumps((CLAUDE.CLAUDE_DIR / "agent.mjs").as_uri())};\n'
                f'serve({{...sdk, query: args => sdk.query({{...args, options: {{...args.options, env: {{...args.options.env, '
                f'ANTHROPIC_API_KEY: "offline", ANTHROPIC_BASE_URL: "http://127.0.0.1:{server.server_port}"}}}}}})}});')
            env={k:os.environ[k] for k in ('PATH','HOME','USER','TMPDIR') if k in os.environ}
            env.update(CLAUDE.RUNTIME_ENV)
            model='anthropic/claude-opus-5.5'
            env['ANTHROPIC_DEFAULT_HAIKU_MODEL']=model
            tool={'name':'confirm_service','description':'Read the service status.',
                  'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}
            events=CLAUDE.new_queue();seen=[]
            with patch.object(CLAUDE,'AGENT',fixture),patch.object(CLAUDE,'gateway_env',return_value=env):
                agent=CLAUDE.ClaudeAgent('goal',events,folder=folder,model=model,thinking_level='medium',
                    max_output_tokens=1024,request_timeout_ms=10000,tools=[tool],active_tools=['confirm_service'],
                    goal_mode='claude_goal',api_base=CLAUDE.AXONHUB_BASE,api_key='offline')
            try:
                CLAUDE.wait_ready(events,['goal'])
                agent.prompt("Complete the user's task.",'/goal The service status is confirmed.')
                while True:
                    _,event=events.get(timeout=30);seen.append(event)
                    self.assertNotEqual(event['type'],'fatal',event)
                    if event['type']=='tool_call':agent.reply(event['id'],output='{"status":"confirmed"}')
                    if event['type']=='settled':
                        self.assertIsNone(event['error_message']);break
                first_requests=len([e for e in seen if e['type']=='request'])
                self.assertLessEqual(first_requests,5)
                raw=[run.load(p) for p in (folder/'native').glob('*.json')]
                self.assertTrue(any(e.get('type')=='goal_progress_guard' and e['paused'] for e in raw))
                self.assertFalse(any(e.get('type')=='native_goal_state' and e['native_goal']['value'].get('met') for e in seen))
                ScriptedMessages.goal_verdicts=[{'ok':True,'reason':'The new service receipt confirms the outcome.'}]
                agent.prompt(json.dumps({'source':'platform_status','event':'relevant_platform_change','status':'A new service receipt is available.'}))
                while True:
                    _,event=events.get(timeout=30);seen.append(event)
                    self.assertNotEqual(event['type'],'fatal',event)
                    if event['type']=='tool_call':agent.reply(event['id'],output='{"status":"confirmed"}')
                    if event['type']=='settled':
                        self.assertIsNone(event['error_message']);break
            finally:agent.close()
            native=[run.load(p) for p in (folder/'native').glob('*.json')]
            self.assertEqual(sum(e['type']=='controller_input' for e in native),2)
            self.assertEqual(sum(e.get('local_command_run',{}).get('command')=='goal' for e in native),1)
            goals=[e['native_goal']['value'] for e in seen if e['type']=='native_goal_state']
            self.assertTrue(any(g.get('met') for g in goals))
            self.assertTrue(all(r['model']==model for r in ScriptedMessages.requests))

    def test_bridge_rejects_unregistered_execution_and_provider_changes(self):
        result = subprocess.run([CLAUDE.node_binary(), '--test', str(CLAUDE.CLAUDE_DIR / 'checks.mjs')],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == '__main__':unittest.main()
