"""Native Claude and Pi mechanism collection against a local scripted API."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

import export_atif
import review
import run


class ChatFixture(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def reply(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply({'data': [{'id': 'local-fixture'}]})

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(request)
        names = [tool['function']['name'] for tool in request.get('tools', [])]
        target = next((name for name in names if name.endswith('confirm_service')), None)
        target = target or next((name for name in names if name.endswith('bash')), None)
        continued = any(message['role'] == 'tool' for message in request['messages'])
        message = {'role': 'assistant', 'content': 'Fixture complete.'}
        if target and not continued:
            arguments = {} if target.endswith('confirm_service') else {
                'command': 'cat /workspace/work-order.json'}
            message = {'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'call_fixture', 'type': 'function', 'function': {
                    'name': target, 'arguments': json.dumps(arguments)}}]}
        self.reply({'id': 'fixture', 'object': 'chat.completion', 'model': request['model'],
                    'choices': [{'index': 0, 'message': message,
                                 'finish_reason': 'tool_calls' if 'tool_calls' in message else 'stop'}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})


class MechanismCollectChecks(unittest.TestCase):
    def test_claude_and_pi_prepare_collect_export_and_review_four_native_sessions(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), ChatFixture)
        server.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}/v1'
        try:
            for harness, model in (('claude-code', 'anthropic/claude-haiku-5.5'),
                                   ('pi-sdk', 'moonshotai/kimi-k3')):
                with self.subTest(harness=harness), TemporaryDirectory() as directory:
                    root = Path(directory); output = root/'output'; registration = root/'registration'
                    key = root/'key'; key.write_text('offline-fixture'); key.chmod(0o600)
                    with patch.dict(run.MODELS, {'subject': model}, clear=True), \
                            patch.object(run, 'registration_path', side_effect=lambda path: Path(path)):
                        run.prepare(output, registration, key, population=4, run_controls=False,
                            study_mode='unified', harness_kind=harness, goal_mode='off', reasoning_effort='high',
                            scenario='engineering-capacity', mechanism='evidence-tampering',
                            api_base=base, api_protocol='chat-completions', served_model='local-fixture')
                    reg = run.load(output/'registration.json')
                    self.assertEqual(reg['mechanism_contract']['path_validation'], 'passed')
                    self.assertEqual({row['native_record_harness'] for row in reg['phase2']['assignments'].values()}, {harness})
                    reg['budget'].update(max_batch_seconds=90, max_actor_seconds=90, request_timeout_seconds=30)
                    run.save(output/'registration.json', reg)
                    run.save(output/'registration-seal.json', {'sha256': run.sha(output/'registration.json')})
                    with patch.object(run, 'verify_collection_freeze'), \
                            patch.object(run, 'registration_path', side_effect=lambda path: Path(path)), \
                            patch.object(run, 'AXONHUB_KEY_FILE', key):
                        run.collect(output, registration, offline_transport_test=True)
                    completion = run.load(output/'completion.json')
                    self.assertIn(completion['status'], ('collected', 'collected_with_limits'))
                    self.assertEqual(completion['failed_transport_attempts'], 0)
                    exported = export_atif.export(output)
                    self.assertEqual(len(exported), 4)
                    self.assertTrue(all(row['native_continuity_passed'] for row in exported))
                    review.review(output)
                    self.assertTrue((output/'independent-review.json').is_file())
                    self.assertTrue((output/'evidence-manifest.json').is_file())
            self.assertTrue(server.requests)
            self.assertTrue(all(request['model'] == 'local-fixture' for request in server.requests))
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
