"""Real Codex threads and containers against a local deterministic protocol fixture."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import codex_gateway
import export_atif
from swarmform.collection import BASH, Collection, save
from swarmform.arrivals import file_hashes


class Responses(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.server.lock:
            self.server.requests.append(request)
            number = len(self.server.requests)
        latest = max(i for i, item in enumerate(request['input']) if item.get('role') == 'user')
        returned = any(i.get('type') == 'function_call_output' for i in request['input'][latest + 1:])
        if returned:
            items = [{'type': 'message', 'id': f'msg-{number}', 'role': 'assistant',
                      'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': 'Fixture finished.'}]}]
        else:
            # This is an offline transport fixture, not generated model behavior.
            command = ('cat /workspace/work-order.md; '
                       'find /workspace/intake -name record.txt -exec cat {} \\;; '
                       'mkdir -p /workspace/releases; '
                       'find /workspace/intake -name record.txt | sort > /workspace/releases/receipt.txt')
            items = [{'type': 'function_call', 'name': 'bash', 'namespace': 'mcp__work',
                      'call_id': f'call-{number}', 'arguments': json.dumps({'command': command})}]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        events = [{'type': 'response.created', 'response': {'id': f'resp-{number}'}}]
        events.extend({'type': 'response.output_item.done', 'output_index': i, 'item': item}
                      for i, item in enumerate(items))
        events.append({'type': 'response.completed', 'response': {'id': f'resp-{number}',
            'status': 'completed', 'model': request['model'], 'output': items,
            'usage': {'input_tokens': 10, 'output_tokens': 3, 'total_tokens': 13}}})
        for event in events:
            self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()


class CollectionChecks(unittest.TestCase):
    def test_three_native_sessions_keep_history_and_only_real_revisions_restart_them(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Responses)
        server.requests, server.lock = [], threading.Lock()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original = codex_gateway.write_config

        def local_config(home, *args):
            original(home, *args)
            path = home / 'config.toml'
            content = path.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1')
            path.write_text(content.replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))

        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(codex_gateway, 'write_config', local_config):
                root = Path(directory)
                actors = ('Northline', 'Aster', 'Meridian')
                offsets = {'opening': 0, 'update': 5, 'close': 10}
                private = {a: {b: {f'intake/{b}/record.txt': f'{a} {b} units 37\n'} for b in offsets} for a in actors}
                inputs = {'startup': {a: {'/workspace/work-order.md': f'Prepare the {a} ledger.'} for a in actors},
                          'private_arrivals': private, 'prompts': {a: [f'Prepare {a} ledger.'] for a in actors}, 'tools': [BASH]}
                harness = codex_gateway.harness_registration('off', 'openai/gpt-5.6-sol')
                registration = {'population': 3, 'model': 'openai/gpt-5.6-sol', 'reasoning': 'high',
                    'harness': harness, 'deployment': {'shared': True}, 'arrival_offsets': offsets,
                    'budget': {'max_batch_seconds': 100, 'max_agent_seconds': 70, 'request_timeout_seconds': 30},
                    'study_mode': 'swarmform', 'research_study': 'SwarmForm', 'plan': {'natural': {a: {} for a in actors}}}
                save(root / 'registration.json', registration)
                collection = Collection(root, registration, inputs, api_key='offline-fixture')
                report = collection.run()
                self.assertIsNone(report['failure'], report)
                self.assertEqual(report['reason'], 'quiescence')
                self.assertEqual(report['terminal_snapshot_count'], 3)
                self.assertEqual(len({s['codex_session']['session_id'] for s in report['actors'].values()}), 3)
                deliveries = json.loads((root / 'source-deliveries.json').read_text())
                self.assertEqual(len(deliveries), 9)
                for record in deliveries:
                    self.assertGreaterEqual(record['delivered_at_monotonic'], record['scheduled_at_monotonic'])
                    self.assertEqual(record['files'], file_hashes(private[record['actor']][record['batch']]))
                for actor in actors:
                    state = report['actors'][actor]
                    self.assertEqual([b for notice in state['notices'] for b in notice['batches']], ['update', 'close'])
                    self.assertGreaterEqual(state['tools'], 2)
                    self.assertLessEqual(state['tools'], 3)
                    self.assertEqual(state['tools'], 1 + len(state['notices']))
                    output = export_atif.export_actor(root, 'natural', actor)
                    self.assertTrue(output['native_continuity_passed'])
                    trajectory = json.loads((root / 'natural' / actor / 'agent/trajectory.json').read_text())
                    self.assertIn('SwarmForm', trajectory['agent']['name'])
                    inputs_seen = [s for s in trajectory['steps'] if s['source'] == 'user']
                    self.assertEqual(len(inputs_seen), 1 + len(state['notices']))
                    self.assertEqual(trajectory['extra']['goal_mode'], 'off')
                with self.assertRaises(FileExistsError):
                    Collection(root, registration, inputs, api_key='offline-fixture').run()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
