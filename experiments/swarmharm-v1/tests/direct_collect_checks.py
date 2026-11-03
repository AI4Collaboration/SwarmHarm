"""Direct HTTP transport and real collector fixtures; no hosted model calls."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request

import run
import export_atif
import direct_api


class Responses(BaseHTTPRequestHandler):
    requests = []
    def log_message(self, *args):
        pass

    def do_POST(self):
        value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append(deepcopy(value))
        number = len(type(self).requests)
        prior = any(v.get('type') == 'function_call_output' for v in value['input'])
        name = 'confirm_service' if value['tools'][0]['name'] == 'confirm_service' else 'bash'
        output = ([{'id': f'm{number}', 'type': 'message', 'role': 'assistant',
                    'status': 'completed', 'content': [{'type': 'output_text',
                    'text': 'Available.' if name == 'confirm_service' else 'Work remains incomplete.', 'annotations': []}]}]
                  if prior else [{'id': f'f{number}', 'type': 'function_call',
                    'call_id': f'c{number}', 'name': name,
                    'arguments': json.dumps({} if name == 'confirm_service' else {'command': 'ls /workspace'}),
                    'status': 'completed'}])
        raw = json.dumps({'id': f'resp{number}', 'object': 'response',
            'model': value['model'], 'status': 'completed', 'output': output,
            'usage': {'input_tokens': 20, 'output_tokens': 10}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class DirectCollectChecks(unittest.TestCase):
    def setUp(self):
        Responses.requests = []
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Responses)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def local_http(self, request, timeout):
        self.assertEqual(request.full_url, direct_api.API_BASE + '/responses')
        # Replace only the HTTP destination in this offline fixture.
        local = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/responses',
            data=request.data, headers=request.headers, method='POST')
        return urllib.request.urlopen(local, timeout=timeout)

    def test_no_preset_and_exact_tool_result_across_turns_and_notice(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(direct_api, 'open_url', self.local_http):
            events = direct_api.new_queue()
            tool = {'type': 'function', 'name': 'confirm_service', 'description': 'Service status',
                    'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}
            agent = direct_api.DirectAgent('a', events, folder=temporary, model='anthropic/claude-haiku-5.5',
                api_base=direct_api.API_BASE, api_key='fixture-secret', thinking_level='high',
                max_output_tokens=16384, context_window=None, request_timeout_ms=1000,
                tools=[tool], active_tools=['confirm_service'])
            self.addCleanup(agent.close)
            self.assertIsNone(direct_api.wait_ready(events, ['a'])['a']['system_prompt'])
            agent.prompt('Business context', 'Complete the filing.')
            for cycle in range(2):
                while True:
                    _, message = events.get(timeout=5)
                    self.assertNotEqual(message['type'], 'fatal', message)
                    if message['type'] == 'tool_call':
                        agent.reply(message['id'], output='{"status":"available","marker":"exact"}')
                    if message['type'] == 'settled':
                        break
                if cycle == 0:
                    agent.prompt('A source record changed.')
            self.assertEqual(len(Responses.requests), 3)
            first, second, third = Responses.requests
            self.assertEqual(first['input'], [{'role': 'user', 'content': 'Business context\n\nComplete the filing.'}])
            returned = next(v for v in second['input'] if v.get('type') == 'function_call_output')
            self.assertEqual(returned['output'], '{"status":"available","marker":"exact"}')
            self.assertEqual(third['input'][-1]['content'], 'A source record changed.')
            self.assertFalse(any(v.get('role') in ('system', 'developer') for v in third['input']))
            for path in Path(temporary).glob('*.json'):
                self.assertNotIn('fixture-secret', path.read_text())

    def test_cli_only_accepts_direct_gateway_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = [sys.executable, '-B', str(run.HERE/'run.py'), '--phase', 'prepare',
                    '--output', str(Path(temporary)/'output'),
                    '--registration-dir', str(run.REGISTRATIONS/'never-created')]
            for options, message in ((['--transport','claude-code'], 'invalid choice'),
                                     (['--api-base','https://api.anthropic.com/v1'], 'All new model calls must use AxonHub')):
                reply = subprocess.run(base+options, capture_output=True, text=True)
                self.assertEqual(reply.returncode, 2)
                self.assertIn(message, reply.stderr)
            self.assertFalse((Path(temporary)/'output').exists())

    def test_http_failure_is_not_retried_or_silently_switched(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(direct_api, 'open_url', side_effect=TimeoutError) as post:
            events = direct_api.new_queue()
            agent = direct_api.DirectAgent('a', events, folder=temporary, model='openai/gpt-6.1-sol',
                api_base=direct_api.API_BASE, api_key='fixture-secret', thinking_level='high',
                max_output_tokens=16384, context_window=None, request_timeout_ms=1000,
                tools=[], active_tools=[])
            self.addCleanup(agent.close)
            direct_api.wait_ready(events, ['a']);agent.prompt('Complete the work.')
            self.assertEqual(events.get(timeout=5)[1]['type'], 'request')
            self.assertEqual(events.get(timeout=5)[1]['event']['type'], 'response.failed')
            self.assertEqual(events.get(timeout=5)[1]['type'], 'fatal')
            self.assertEqual(post.call_count, 1)

    def test_common_prepare_collect_export_without_any_harness(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(direct_api, 'open_url', self.local_http):
            root = Path(temporary) / 'rollout'
            registration = run.REGISTRATIONS / ('test-direct-' + Path(temporary).name)
            self.addCleanup(shutil.rmtree, registration, True)
            key = Path(temporary) / 'key';key.write_text('fixture-secret')
            with patch.object(run, 'verify_routes', return_value={}):
                run.prepare(root, registration, key, run_controls=False, study_mode='phase1')
            reg = run.load(root/'registration.json')
            self.assertEqual(reg['harness']['kind'], 'direct-api')
            reg['source_publication'] = None
            reg['completion_protocol']['unfinished_work_followup_seconds'] = 0
            run.save(root/'registration.json', reg)
            run.save(root/'registration-seal.json', {'sha256': run.sha(root/'registration.json')})
            with patch.object(run, 'verify_collection_freeze'), patch.object(run, 'AXONHUB_KEY_FILE', key):
                run.collect(root, registration)
            completion = run.load(root/'completion.json')
            self.assertIn(completion['status'], ('collected', 'collected_with_limits'), completion)
            initial = run.load(root/'initial-input-audit.json')['natural']
            for actor in reg['plan']['natural']:
                folder = root/'natural'/actor
                first = run.load(folder/'trace/0001.request.json')
                self.assertEqual(first['input'], [{'role': 'user', 'content': '\n\n'.join(v['content'] for v in initial[actor]['input'])}])
                self.assertFalse((folder/'claude').exists() or (folder/'pi').exists() or (folder/'codex').exists())
            self.assertEqual(len(export_atif.export(root)), 4)


if __name__ == '__main__':
    unittest.main()
