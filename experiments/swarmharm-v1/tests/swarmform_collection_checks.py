"""Real Codex threads and containers against a local deterministic protocol fixture."""

from hashlib import sha256
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
from swarmform.inputs import WORKSTATION_PERMISSIONS


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
        if not returned and self.server.wait_for_arrivals:
            if not self.server.deliveries_ready.wait(timeout=25):
                raise TimeoutError('Fixture deliveries did not complete')
        if returned:
            items = [{'type': 'message', 'id': f'msg-{number}', 'role': 'assistant',
                      'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': 'Fixture finished.'}]}]
        else:
            # This is an offline transport fixture, not generated model behavior.
            command = ('cat /workspace/work-order.md; '
                       'find /workspace/intake -name record.txt -exec cat {} \\;; '
                       'mkdir -p /workspace/releases; '
                       'find /workspace/intake -name record.txt | sort > /workspace/releases/receipt.txt')
            if command_for := getattr(self.server, 'command_for', None):
                command = command_for(request)
            items = [{'type': 'function_call', 'name': 'bash', 'namespace': 'mcp__work',
                      'call_id': f'call-{number}', 'arguments': json.dumps({'command': command}, separators=(',', ':'))}]
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
    def test_cleanup_keeps_first_fault_and_records_all_later_errors(self):
        from unittest.mock import Mock
        actors = ('A', 'B', 'C')
        inputs = {'startup': dict.fromkeys(actors, {}), 'prompts': dict.fromkeys(actors, ['task']),
                  'private_arrivals': dict.fromkeys(actors, {}), 'tools': []}
        reg = {'population': 3, 'harness': {'goal_mode': 'off'},
               'model': 'offline', 'reasoning': 'high', 'deployment': {'shared': True},
               'budget': {'max_batch_seconds': 60, 'request_timeout_seconds': 30}}
        class Deployment:
            bindings = {}
            def __init__(self, *args, **kwargs): pass
            def close(self): raise OSError('terminal snapshot failed')
        for primary in (RuntimeError('original runtime fault'), KeyboardInterrupt()):
            with self.subTest(primary=type(primary).__name__), tempfile.TemporaryDirectory() as directory:
                agents = []
                def agent_class(*args, **kwargs):
                    agent = Mock();agent.close.side_effect = RuntimeError('close failed')
                    agents.append(agent);return agent
                collection = Collection(directory, reg, inputs, api_key='offline',
                    agent_class=agent_class, deployment_class=Deployment)
                collection.close_continuation = Mock(side_effect=ValueError('last scan failed'))
                with patch('swarmform.collection.wait_ready', side_effect=primary):
                    result = collection.run()
                self.assertEqual(result['reason'], 'interrupted' if isinstance(primary, KeyboardInterrupt) else 'runtime_failure')
                self.assertEqual(result['failure']['message'], str(primary))
                self.assertEqual(result['failure'], json.loads((Path(directory) / 'failure.json').read_text()))
                self.assertEqual([x['type'] for x in result['shutdown_errors']],
                    ['ContinuationShutdown', 'NativeShutdown', 'NativeShutdown', 'NativeShutdown', 'DeploymentShutdown'])
                self.assertEqual([x['actor'] for x in result['shutdown_errors'] if 'actor' in x], list(actors))
                for agent in agents: agent.close.assert_called_once()
                self.assertTrue((Path(directory) / 'completion.json').exists())

    def test_cleanup_failure_alone_cannot_be_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            c = Collection.__new__(Collection)
            c.root, c.failure, c.reason, c.shutdown_errors = Path(directory), None, 'quiescence', []
            c.shutdown_failure('CommandShutdown', OSError('result unavailable'), actor='A')
            self.assertEqual(c.reason, 'runtime_failure')
            self.assertEqual(c.failure['actor'], 'A')
            self.assertEqual(json.loads((c.root / 'failure.json').read_text()), c.failure)

    def test_three_native_sessions_keep_history_and_only_real_revisions_restart_them(self):
        for model in ('openai/gpt-5.6-sol', 'openai/gpt-6.1-sol'):
            with self.subTest(model=model):
                self.check_native_sessions(model)

    def test_busy_sessions_do_not_restart_after_accessing_the_delivered_updates(self):
        for model in ('openai/gpt-5.6-sol', 'openai/gpt-6.1-sol'):
            with self.subTest(model=model):
                self.check_native_sessions(model, wait_for_arrivals=True)

    def check_native_sessions(self, model, *, wait_for_arrivals=False):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Responses)
        server.requests, server.lock = [], threading.Lock()
        server.wait_for_arrivals = wait_for_arrivals
        server.deliveries_ready = threading.Event()
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
                harness = codex_gateway.harness_registration('off', model)
                registration = {'population': 3, 'model': model, 'reasoning': 'high',
                    'workstation_permissions': WORKSTATION_PERMISSIONS,
                    'harness': harness, 'deployment': {'shared': True}, 'arrival_offsets': offsets,
                    'budget': {'max_batch_seconds': 100, 'max_agent_seconds': 70, 'request_timeout_seconds': 30},
                    'study_mode': 'swarmform', 'research_study': 'SwarmForm', 'plan': {'natural': {a: {} for a in actors}}}
                save(root / 'registration.json', registration)
                class FixtureCollection(Collection):
                    def deliver_arrivals(self, deployment):
                        super().deliver_arrivals(deployment)
                        if self.schedule.all_delivered:
                            server.deliveries_ready.set()

                collection = FixtureCollection(root, registration, inputs, api_key='offline-fixture')
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
                    notified = {b for notice in state['notices'] for b in notice['batches']}
                    accessed = {b for a, b in collection.schedule.accessed if a == actor}
                    self.assertEqual(notified | accessed, {'update', 'close'})
                    self.assertFalse(notified & accessed)
                    for batch in accessed:
                        for receipt in collection.schedule.accessed[(actor, batch)]['reads'].values():
                            self.assertFalse(Path(receipt['observation']).is_absolute())
                            raw = (root / receipt['observation']).read_bytes()
                            self.assertEqual(sha256(raw).hexdigest(), receipt['observation_sha256'])
                    if wait_for_arrivals:
                        self.assertEqual(state['notices'], [])
                        self.assertEqual(accessed, {'update', 'close'})
                        self.assertEqual(state['tools'], 1)
                    self.assertGreaterEqual(state['tools'], 1)
                    self.assertLessEqual(state['tools'], 3)
                    self.assertEqual(state['tools'], 1 + len(state['notices']))
                    output = export_atif.export_actor(root, 'natural', actor)
                    self.assertTrue(output['native_continuity_passed'])
                    trajectory = json.loads((root / 'natural' / actor / 'agent/trajectory.json').read_text())
                    self.assertIn('SwarmForm', trajectory['agent']['name'])
                    inputs_seen = [s for s in trajectory['steps'] if s['source'] == 'user']
                    self.assertEqual(len(inputs_seen), 1 + len(state['notices']))
                    self.assertEqual(trajectory['extra']['goal_mode'], 'off')
                    native = [json.loads(p.read_text())['message'] for p in sorted((root / 'natural' / actor / 'codex/native').glob('*.json'))]
                    started = next(m for m in native if m.get('method') == 'thread/start')
                    self.assertEqual(started['params']['sandbox'], 'workspace-write')
                    turns = [m for m in native if m.get('method') == 'turn/start']
                    self.assertTrue(all(m['params']['sandboxPolicy'] == WORKSTATION_PERMISSIONS for m in turns))
                rendered = json.dumps(server.requests)
                self.assertIn('workspace-write', rendered)
                self.assertNotIn('sandbox_mode` is `read-only', rendered)
                with self.assertRaises(FileExistsError):
                    Collection(root, registration, inputs, api_key='offline-fixture').run()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
