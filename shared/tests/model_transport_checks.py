import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api_transport import ChatBridge, chat_request, responses_reply, response_events, messages_reply, message_events
from model_lineup import selection
from guardrails import native_harness
import claude_agent


class TransportChecks(unittest.TestCase):
    def test_all_eleven_have_matching_harness_and_claude_accepts_external_endpoint(self):
        rows = selection()
        self.assertEqual(len(rows), 11)
        for row in rows:
            self.assertEqual(native_harness({'model': row['model']}), row['harness'])
        env = claude_agent.gateway_env('https://example.test/proxy/v1', 'local-test',
                                     'anthropic/claude-haiku-5.5', '/tmp/private-test')
        self.assertEqual(env['ANTHROPIC_BASE_URL'], 'https://example.test/proxy')
        self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'], 'local-test')

    def test_namespaces_history_and_reasoning_survive_tool_roundtrip(self):
        body = {'instructions': 'Original instructions', 'reasoning': {'effort': 'high'},
            'tools': [{'type': 'namespace', 'name': 'work', 'description': 'Business tools',
                       'tools': [{'type': 'function', 'name': 'read', 'parameters': {'type': 'object'}}]}],
            'input': [{'role': 'user', 'content': 'Original task'},
                      {'type': 'function_call', 'namespace': 'work', 'name': 'read', 'call_id': 'c1', 'arguments': '{}'},
                      {'type': 'function_call_output', 'call_id': 'c1', 'output': 'Exact result'}]}
        cache = {'c1': {'reasoning_content': 'retained', 'reasoning_details': [{'signature': 'original'}]}}
        request = chat_request(body, 'responses', 'served-id', cache)
        self.assertEqual(request['model'], 'served-id')
        self.assertEqual(request['reasoning_effort'], 'high')
        self.assertEqual(request['tools'][0]['function']['name'], 'work__read')
        self.assertEqual(request['messages'][-2]['tool_calls'][0]['function']['name'], 'work__read')
        self.assertEqual(request['messages'][-2]['reasoning_details'], cache['c1']['reasoning_details'])
        self.assertEqual(request['messages'][-1]['content'], 'Exact result')

    def test_messages_preserves_multiple_calls_and_exact_results(self):
        body = {'system': [{'type': 'text', 'text': 'System'}], 'messages': [
            {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'a', 'name': 'read', 'input': {'x': 1}},
                                              {'type': 'tool_use', 'id': 'b', 'name': 'read', 'input': {'x': 2}}]},
            {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'a', 'content': 'one'},
                                        {'type': 'tool_result', 'tool_use_id': 'b', 'content': 'two'}]}]}
        request = chat_request(body, 'messages', 'same-model', {})
        self.assertEqual([m['tool_call_id'] for m in request['messages'][-2:]], ['a', 'b'])
        self.assertEqual(len(request['messages'][1]['tool_calls']), 2)

    def test_finish_and_usage_are_preserved(self):
        data = {'choices': [{'message': {'content': 'done'}, 'finish_reason': 'length'}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
        response = responses_reply(data, 'model')
        self.assertEqual(response['status'], 'incomplete')
        self.assertEqual(list(response_events(response))[-1]['type'], 'response.incomplete')
        message = messages_reply(data, 'model')
        self.assertEqual(message['stop_reason'], 'max_tokens')
        self.assertEqual(list(message_events(message))[-2]['usage']['output_tokens'], 5)

    def test_unimplemented_content_is_rejected_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            chat_request({'input': [{'role': 'user', 'content': [{'type': 'input_image'}]}]}, 'responses', 'm', {})
        with self.assertRaises(ValueError):
            chat_request({'previous_response_id': 'opaque'}, 'responses', 'm', {})

    def test_nullable_integer_and_null_strings_coerce_without_touching_string_fields(self):
        schemas = {'execute_dispatch': {'type': 'object', 'properties': {
            'revision': {'type': 'integer'},
            'batch_size': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 4},
            'note': {'type': ['string', 'null']}}}}
        data = {'choices': [{'message': {'tool_calls': [
            {'id': 'c1', 'type': 'function', 'function': {
                'name': 'execute_dispatch', 'arguments': '{"batch_size":"4","revision":"8","note":"4"}'}}]},
            'finish_reason': 'tool_calls'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5, 'total_tokens': 10}}
        resp = responses_reply(data, 'z-ai/glm-5.3', schemas)
        parsed = json.loads(resp['output'][0]['arguments'])
        self.assertEqual(parsed, {'batch_size': 4, 'revision': 8, 'note': '4'})
        null_data = {'choices': [{'message': {'tool_calls': [
            {'id': 'c2', 'type': 'function', 'function': {
                'name': 'execute_dispatch', 'arguments': '{"batch_size":"null","revision":8,"note":"null"}'}}]},
            'finish_reason': 'tool_calls'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5, 'total_tokens': 10}}
        parsed_null = json.loads(responses_reply(null_data, 'z-ai/glm-5.3', schemas)['output'][0]['arguments'])
        self.assertEqual(parsed_null, {'batch_size': None, 'revision': 8, 'note': 'null'})

    def test_chat_bridge_retries_transient_429_and_502_but_never_retries_400(self):
        events = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def do_POST(self):
                events.append(len(events) + 1)
                step = self.server.responses.pop(0)
                status, payload, headers = step
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                server.responses = [
                    (429, {'error': {'message': 'rate limit'}}, {'Retry-After': '0.01'}),
                    (502, {'error': {'message': 'bad gateway'}}, {}),
                    (200, {'model': 'openai/gpt-6.1-sol',
                           'choices': [{'message': {'content': 'Recovered'}, 'finish_reason': 'stop'}],
                           'usage': {'prompt_tokens': 4, 'completion_tokens': 2, 'total_tokens': 6}}, {}),
                ]
                bridge = ChatBridge(f'http://127.0.0.1:{server.server_port}/v1', 'secret',
                                    'openai/gpt-6.1-sol', tmp, max_attempts=4, retry_backoff=0.01)
                try:
                    req = urllib.request.Request(
                        bridge.base + '/responses',
                        data=json.dumps({'model': 'openai/gpt-6.1-sol',
                                         'input': [{'role': 'user', 'content': 'hi'}]}).encode(),
                        headers={'Authorization': 'Bearer ' + bridge.token, 'Content-Type': 'application/json'})
                    reply = json.load(urllib.request.urlopen(req, timeout=10))
                    self.assertEqual(reply['output'][0]['content'][0]['text'], 'Recovered')
                    self.assertEqual(len(events), 3)

                    events.clear()
                    server.responses = [(400, {'error': {'message': 'invalid request'}}, {})]
                    bad_req = urllib.request.Request(
                        bridge.base + '/responses',
                        data=json.dumps({'model': 'openai/gpt-6.1-sol',
                                         'input': [{'role': 'user', 'content': 'hi'}]}).encode(),
                        headers={'Authorization': 'Bearer ' + bridge.token, 'Content-Type': 'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as ctx:
                        urllib.request.urlopen(bad_req, timeout=10)
                    self.assertEqual(ctx.exception.code, 400)
                    self.assertEqual(len(events), 1)
                finally:
                    bridge.close()
                captured = json.load(gzip.open(Path(tmp) / '000001.json.gz', 'rt'))
                self.assertEqual([r['status'] for r in captured['retry_history']], [429, 502])
        finally:
            server.shutdown(); server.server_close()

    def test_openai_compatible_priority_and_axonhub_fallback(self):
        from guardrails import AXONHUB_API_BASE, OPENROUTER_API_BASE, resolve_api_base, resolve_api_key, resolve_axonhub_fallback
        from unittest.mock import patch

        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(resolve_api_base(), AXONHUB_API_BASE)
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'sk-or-test'}, clear=True):
            self.assertEqual(resolve_api_base(), OPENROUTER_API_BASE)
            self.assertEqual(resolve_api_key(api_base=OPENROUTER_API_BASE), 'sk-or-test')
        with patch.dict('os.environ', {'OPENAI_BASE_URL': 'https://custom.example/v1',
                                       'OPENROUTER_API_KEY': 'sk-or-test',
                                       'OPENAI_API_KEY': 'sk-custom',
                                       'AXONHUB_API_KEY': 'sk-axon'}, clear=True):
            self.assertEqual(resolve_api_base(), 'https://custom.example/v1')
            self.assertEqual(resolve_api_key(api_base='https://custom.example/v1'), 'sk-custom')
            self.assertEqual(resolve_axonhub_fallback('https://custom.example/v1', 'sk-custom'),
                             (AXONHUB_API_BASE, 'sk-axon'))

        # Test runtime failover: primary returns 404 (e.g. blocked model on OpenRouter), fallback AxonHub returns 200
        def make_server(queue_list, log_list):
            class H(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def do_POST(self):
                    code, payload = queue_list.pop(0)
                    log_list.append((self.headers.get('Authorization'), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                    raw = json.dumps(payload).encode()
                    self.send_response(code); self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(raw))); self.end_headers()
                    self.wfile.write(raw)
            srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            return srv

        p_log, f_log = [], []
        p_srv = make_server([(404, {'error': {'message': 'No endpoints available', 'code': 404}})], p_log)
        f_srv = make_server([(200, {'model': 'openai/gpt-6.1-sol-20261101',
                                    'choices': [{'message': {'content': 'AxonHub rescued'}, 'finish_reason': 'stop'}],
                                    'usage': {'prompt_tokens': 5, 'completion_tokens': 3}})], f_log)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                bridge = ChatBridge(f'http://127.0.0.1:{p_srv.server_port}/v1', 'or-key',
                                    'openai/gpt-6.1-sol', tmp, max_attempts=2, retry_backoff=0.01,
                                    fallback=(f'http://127.0.0.1:{f_srv.server_port}/v1', 'axon-key'))
                try:
                    req = urllib.request.Request(
                        bridge.base + '/responses',
                        data=json.dumps({'model': 'openai/gpt-6.1-sol',
                                         'input': [{'role': 'user', 'content': 'hello'}]}).encode(),
                        headers={'Authorization': 'Bearer ' + bridge.token, 'Content-Type': 'application/json'})
                    reply = json.load(urllib.request.urlopen(req, timeout=10))
                    self.assertEqual(reply['output'][0]['content'][0]['text'], 'AxonHub rescued')
                    self.assertEqual(reply['usage']['total_tokens'], 8)
                    self.assertEqual(len(p_log), 1)
                    self.assertEqual(len(f_log), 1)
                    self.assertEqual(f_log[0][0], 'Bearer axon-key')
                finally:
                    bridge.close()
                cap = json.load(gzip.open(Path(tmp) / '000001.json.gz', 'rt'))
                self.assertTrue(cap['axonhub_fallback_used'])
        finally:
            p_srv.shutdown(); p_srv.server_close()
            f_srv.shutdown(); f_srv.server_close()


if __name__ == '__main__':
    unittest.main()
