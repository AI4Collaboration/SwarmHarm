"""Subscription guards and offline collection through the real Claude Agent SDK."""
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import export_atif
import launch
import run

CLAUDE = run.claude_agent
MODEL = 'claude-offline-fixture-1'


class SubscriptionChecks(unittest.TestCase):
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

    def test_claude_launcher_needs_no_api_key(self):
        with patch.object(launch, 'collector_python', return_value='/python'):
            argv = launch.collector_command('/tmp/study', '/tmp/registration')
        self.assertNotIn('--key-file', argv)


class ScriptedMessages(BaseHTTPRequestHandler):
    """Local Anthropic protocol fixture. No requests leave localhost."""
    requests = []

    def log_message(self, *args):pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append(body)
        tools = [tool['name'] for tool in body.get('tools', [])]
        number = len(type(self).requests)
        phase2 = 'mcp__continuation__read_service_calendar' in tools
        target = ('mcp__continuation__read_service_calendar' if phase2
                  else 'mcp__work__confirm_service' if tools == ['mcp__work__confirm_service']
                  else 'mcp__work__bash')
        already = any(message.get('role') == 'assistant' and isinstance(message.get('content'), list)
                      and any(block.get('name') == target for block in message['content'])
                      for message in body['messages'])
        if not already:
            block = {'type': 'tool_use', 'id': f'toolu_{number}', 'name': target, 'input': {}}
            if target.endswith('__bash'):block['input'] = {'command': 'ls /workspace'}
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
        if target.endswith('__bash') and not already:
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


@unittest.skipUnless(shutil.which('claude') and shutil.which('node')
    and (CLAUDE.CLAUDE_DIR / 'node_modules/@anthropic-ai/claude-agent-sdk/package.json').exists(),
    'Claude Code, Node.js and the optional Claude SDK install required')
class ClaudeCollectChecks(unittest.TestCase):
    def test_bridge_rejects_unregistered_execution_and_provider_changes(self):
        result = subprocess.run([CLAUDE.node_binary(), '--test', str(CLAUDE.CLAUDE_DIR / 'checks.mjs')],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_sdk_collection_and_atif_preserve_native_messages(self):
        ScriptedMessages.requests = []
        server = ThreadingHTTPServer(('127.0.0.1', 0), ScriptedMessages)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as patches:
            root = Path(os.environ.get('SWARMHARM_KEEP_CLAUDE_COLLECT') or temporary) / 'study'
            registration = run.REGISTRATIONS / ('test-claude-' + Path(temporary).name)
            self.addCleanup(shutil.rmtree, registration, True)
            # Test-only query wrapper: exercise the real SDK/CLI with a localhost
            # protocol fixture. Production has no API-key or base-URL option.
            fixture = Path(temporary) / 'offline-agent.mjs'
            fixture.write_text(
                f'import * as sdk from {json.dumps((CLAUDE.CLAUDE_DIR / "node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs").as_uri())};\n'
                f'import {{serve}} from {json.dumps((CLAUDE.CLAUDE_DIR / "agent.mjs").as_uri())};\n'
                f'serve({{...sdk, query: (args) => sdk.query({{...args, options: {{...args.options, env: {{...args.options.env, '
                f'ANTHROPIC_API_KEY: "offline-fixture-key", ANTHROPIC_BASE_URL: "http://127.0.0.1:{server.server_port}"}}}}}})}});\n')
            clean_env = {name: os.environ[name] for name in ('PATH', 'HOME', 'USER', 'TMPDIR') if name in os.environ}
            clean_env.update(CLAUDE.RUNTIME_ENV)
            patches.enter_context(patch.object(CLAUDE, 'AGENT', fixture))
            patches.enter_context(patch.object(CLAUDE, 'subscription_env', return_value=clean_env))
            patches.enter_context(patch.object(CLAUDE, 'subscription_auth', return_value={
                'logged_in': True, 'auth_method': 'claude.ai', 'api_provider': 'firstParty'}))
            patches.enter_context(patch.object(run, 'MODELS', {'claude': MODEL}))
            patches.enter_context(patch.object(run, 'UPSTREAM_MODELS', {'claude': MODEL}))
            routes = patches.enter_context(patch.object(run, 'verify_routes', side_effect=AssertionError('AxonHub must not be called')))
            run.prepare(root, registration, None, run_controls=False, harness_kind='claude-code')
            reg = run.load(root / 'registration.json')
            self.assertIsNone(reg['api_base'])
            self.assertEqual(reg['harness']['authentication'], 'claude-subscription')
            reg['budget'].update(max_batch_seconds=120, max_actor_seconds=120)
            if reg.get('source_publication'):reg['source_publication']['after_start_seconds'] = 1
            run.save(root / 'registration.json', reg)
            run.save(root / 'registration-seal.json', {'sha256': run.sha(root / 'registration.json')})
            patches.enter_context(patch.object(run, 'verify_collection_freeze'))
            patches.enter_context(patch.object(run, 'AXONHUB_KEY_FILE', None))
            run.collect(root, registration)
            routes.assert_not_called()
            completion = run.load(root / 'completion.json')
            self.assertIn(completion['status'], {'collected', 'collected_with_limits'}, completion)
            results = export_atif.export(root)
            self.assertEqual(len(results), 4)
            for actor in reg['plan']['natural']:
                folder = root / 'natural' / actor
                result = run.load(folder / 'result.json')
                self.assertEqual(result['tools'], 2)
                trajectory = run.load(folder / 'agent/trajectory.json')
                self.assertFalse(trajectory['extra']['provider_http_payloads_captured'])
                self.assertFalse(trajectory['extra']['provider_context_continuity_verified'])
                deliveries=[value for step in trajectory['steps'] if step['source']=='agent'
                            for value in step['extra']['tool_result_delivery'].values()]
                self.assertTrue(deliveries)
                self.assertTrue(all(value['sdk_delivery_verified'] for value in deliveries))
                self.assertTrue(list((folder / 'claude/native').glob('*.json')))
                native = [run.load(path) for path in (folder / 'claude/native').glob('*.json')]
                identities = {value['session_id'] for value in native if value.get('session_id')}
                self.assertEqual(identities, {result['claude_session']['session_id']})
                # Native evidence must reject altered controller-side tool arguments.
                first=folder/'trace/0001.response.json';original=first.read_bytes()
                changed=run.load(first)
                next(item for item in changed['output'] if item['type']=='function_call')['arguments']='{"command":"false"}'
                try:
                    run.save(first,changed)
                    with self.assertRaisesRegex(AssertionError,'native tool calls'):
                        export_atif.claude_native_evidence(folder,sorted((folder/'trace').glob('????.request.json')))
                finally:first.write_bytes(original)
            self.assertTrue(ScriptedMessages.requests)
            self.assertTrue(all(all(tool['name'].startswith('mcp__work__')
                                   for tool in request.get('tools', []))
                                for request in ScriptedMessages.requests))
            # Check live tool replacement and new streaming input on the SAME SDK
            # query. This transport test does not assert a behavioral Phase 1 gate.
            tool = lambda name: {'type': 'function', 'name': name, 'description': 'Read the service status.',
                'parameters': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}}
            events = CLAUDE.new_queue()
            agent = CLAUDE.ClaudeAgent('continuity', events, folder=Path(temporary) / 'continuity',
                model=MODEL, thinking_level='high', max_output_tokens=1024,
                request_timeout_ms=10000, tools=[tool('confirm_service'), tool('read_service_calendar')],
                active_tools=['confirm_service'], job_context=None, goal_mode='off')
            try:
                ready = CLAUDE.wait_ready(events, ['continuity'])['continuity']
                requests = []
                def settle():
                    while True:
                        _, message = events.get(timeout=30)
                        if message['type'] == 'request':requests.append(message['payload'])
                        elif message['type'] == 'tool_call':agent.reply(message['id'], output='{"status":"available"}')
                        elif message['type'] == 'settled':
                            self.assertFalse(message.get('error_message'), message)
                            return
                        elif message['type'] in ('fatal', 'closed', 'exited'):self.fail(str(message))
                agent.prompt('Check the service.')
                settle()
                first_count = len(requests)
                agent.set_tools(['confirm_service', 'read_service_calendar'])
                agent.prompt('Review the updated service calendar.')
                settle()
                self.assertGreater(len(requests), first_count)
                self.assertIn('read_service_calendar', [tool['name'] for tool in requests[-1]['tools']])
                self.assertTrue(any(item.get('type') == 'function_call_output'
                                    for item in requests[first_count]['input']))
                native = [run.load(path) for path in (Path(temporary) / 'continuity/native').glob('*.json')]
                self.assertEqual({value['session_id'] for value in native if value.get('session_id')}, {ready['session_id']})
            finally:agent.close()


if __name__ == '__main__':unittest.main()
