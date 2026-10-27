"""Offline end-to-end collection through real Pi SDK sessions and a scripted Responses server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

import export_atif
import lab
import run

PI = run.pi_agent
GOAL_ID = re.compile(r'<goal_id>\n([^\n]+)\n</goal_id>')


def _text(item):
    content = item.get('content', '')
    return content if isinstance(content, str) else '\n'.join(part.get('text', '') for part in content)


class ScriptedResponses(BaseHTTPRequestHandler):
    """Preflight calls confirm_service; subjects list the workspace once, then answer."""

    requests = []
    # Subject requests to fail once with the transient error OpenRouter returned on 27 October.
    fail_subject_requests = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append(body)
        tools = [tool['name'] for tool in body.get('tools', [])]
        outputs = [item for item in body['input'] if item.get('type') == 'function_call_output']
        goal = next((GOAL_ID.search(_text(item)) for item in reversed(body['input'])
                     if item.get('role') == 'user' and GOAL_ID.search(_text(item))), None)
        number = len(type(self).requests)
        if tools != ['confirm_service'] and type(self).fail_subject_requests:
            type(self).fail_subject_requests -= 1
            return self.stream([{'type': 'response.failed', 'response': {
                'id': f'resp_{number}', 'object': 'response', 'status': 'failed', 'model': body['model'],
                'output': [], 'error': {'code': 'server_error', 'message': 'Sorry, something went wrong.'}}}])
        if tools == ['confirm_service']:
            item = self.call('confirm_service', {}, number) if not outputs else self.message('available', number)
        elif not outputs:
            item = self.call('bash', {'command': 'ls /workspace'}, number)
        elif goal and 'goal_complete' in tools and len(outputs) == 1:
            item = self.call('goal_complete', {'goal_id': goal.group(1), 'summary': 'Listed the workspace.'}, number)
        else:
            item = self.message('The workspace is listed.', number)
        response = {
            'id': f'resp_{number}', 'object': 'response', 'status': 'completed', 'model': body['model'],
            'output': [item], 'usage': {
                'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15,
                'input_tokens_details': {'cached_tokens': 0},
                'output_tokens_details': {'reasoning_tokens': 0}}}
        events = [
            {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
            {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
            {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
            {'type': 'response.completed', 'response': response},
        ]
        self.stream(events)

    def stream(self, events):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for event in events:
            self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())

    @staticmethod
    def call(name, arguments, number):
        return {'type': 'function_call', 'id': f'fc_{number}', 'call_id': f'call_{number}',
                'name': name, 'arguments': json.dumps(arguments), 'status': 'completed'}

    @staticmethod
    def message(text, number):
        return {'type': 'message', 'id': f'msg_{number}', 'role': 'assistant', 'status': 'completed',
                'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}


@unittest.skipUnless(
    os.environ.get('SWARMHARM_NODE') or shutil.which('node'), 'Node.js is required for Pi sessions')
class PiCollectChecks(unittest.TestCase):
    def setUp(self):
        ScriptedResponses.requests = []
        ScriptedResponses.fail_subject_requests = 0
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), ScriptedResponses)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}/v1'

    def collect(self, temporary, goal_mode):
        root = Path(os.environ.get('SWARMHARM_KEEP_PI_COLLECT') or temporary) / 'study'
        registration = run.REGISTRATIONS / ('test-' + Path(temporary).name)
        self.addCleanup(shutil.rmtree, registration, True)
        key = Path(temporary) / 'key'
        key.write_text('test-key')
        key.chmod(0o600)
        with patch.object(run, 'verify_routes', return_value={}):
            run.prepare(root, registration, key, run_controls=False, goal_mode=goal_mode)
        reg = run.load(root / 'registration.json')
        reg['budget']['max_batch_seconds'] = 240
        reg['budget']['max_actor_seconds'] = 240
        if reg.get('source_publication'):
            reg['source_publication']['after_start_seconds'] = 5
        run.save(root / 'registration.json', reg)
        run.save(root / 'registration-seal.json', {'sha256': run.sha(root / 'registration.json')})
        with patch.object(run, 'verify_collection_freeze'), \
                patch.object(run, 'registration_api_base', return_value=self.base), \
                patch.object(run, 'AXONHUB_KEY_FILE', key):
            run.collect(root, registration)
        return root, reg

    def assert_native_records(self, root, reg):
        completion = run.load(root / 'completion.json')
        self.assertIn(completion['status'], {'collected', 'collected_with_limits'}, completion)
        world = run.load(root / 'natural/world.json')
        for actor, item in reg['plan']['natural'].items():
            trace = root / 'natural' / actor / 'trace'
            first = run.load(trace / '0001.request.json')
            system = first['input'][0]
            self.assertEqual(system['role'], 'developer')
            self.assertEqual(system['content'],
                             run.load(root / 'natural' / actor / 'pi-system-prompt.json')['system_prompt'])
            self.assertTrue(system['content'].startswith(PI.PREAMBLE))
            self.assertNotIn('coding agent harness', system['content'])
            self.assertNotIn('<docs>', system['content'])
            self.assertIn('<cwd>\n/workspace\n</cwd>', system['content'])
            self.assertIn(json.loads(run.load(root / 'initial-input-audit.json')['natural'][actor]['input'][0]['content'])['job_id'],
                          system['content'])
            names = [tool['name'] for tool in first['tools']]
            self.assertEqual(names[:len(lab.tools(item))], [tool['name'] for tool in lab.tools(item)])
            self.assertFalse({'read', 'edit', 'write', 'grep', 'find', 'ls', 'powershell'} & set(names))
            tool = run.load(trace / '0001-tool-1.json')
            self.assertEqual(tool['name'], 'bash')
            event = next(row for row in world['events'] if row['id'] == tool['event_id'])
            self.assertEqual((event['actor'], event['operation']), (actor, 'bash'))
            self.assertEqual(json.dumps(tool['result'], ensure_ascii=False),
                             next(entry['output'] for entry in run.load(trace / '0002.request.json')['input']
                                  if entry.get('type') == 'function_call_output'
                                  and entry['call_id'] == tool['call_id']))
        results = export_atif.export(root)
        self.assertEqual(len(results), len(reg['plan']['natural']))
        return results

    def test_plain_prompt_campaign_runs_through_pi_and_exports_atif(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, reg = self.collect(temporary, 'off')
            self.assertEqual(reg['harness']['goal_mode'], 'off')
            self.assertTrue(run.load(root / 'preflight/glm/summary.json')['passed'])
            self.assert_native_records(root, reg)
            for actor in reg['plan']['natural']:
                first = run.load(root / 'natural' / actor / 'trace/0001.request.json')
                task = run.load(root / 'initial-input-audit.json')['natural'][actor]['input'][1]['content']
                self.assertEqual(_text(first['input'][1]), task)
                self.assertNotIn('goal_complete', [tool['name'] for tool in first['tools']])

    def test_goal_command_campaign_sends_task_through_pi_goal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, reg = self.collect(temporary, 'goal_command')
            self.assertEqual(reg['harness']['extension_tools'], PI.GOAL_TOOLS)
            self.assert_native_records(root, reg)
            for actor in reg['plan']['natural']:
                first = run.load(root / 'natural' / actor / 'trace/0001.request.json')
                self.assertTrue(_text(first['input'][1]).startswith('Goal mode is active.'))
                self.assertTrue(set(PI.GOAL_TOOLS) <= {tool['name'] for tool in first['tools']})
                trajectory = run.load(root / 'natural' / actor / 'agent/trajectory.json')
                calls = [call['function_name'] for step in trajectory['steps'] for call in step.get('tool_calls', [])]
                self.assertIn('goal_complete', calls)

    def test_transient_provider_error_is_retried_within_the_same_request(self):
        ScriptedResponses.fail_subject_requests = 1
        with tempfile.TemporaryDirectory() as temporary:
            root, reg = self.collect(temporary, 'off')
            self.assertEqual(reg['harness']['settings']['retry']['maxRetries'], 3)
            results = self.assert_native_records(root, reg)
            retried = [actor for actor in reg['plan']['natural']
                       if run.load(root / 'natural' / actor / 'result.json')['provider_retries']]
            self.assertEqual(len(retried), 1)
            attempts = root / 'natural' / retried[0] / 'trace/transport-attempts'
            failed = list(attempts.glob('*/0001.error.json'))
            self.assertEqual(len(failed), 1)
            label = failed[0].parent
            self.assertTrue((label / '0002.response.json').exists())
            self.assertTrue((root / 'natural' / retried[0] / 'trace' / f'{label.name}.response.json').exists())
            self.assertFalse(list((root / 'natural' / retried[0] / 'trace').glob('*.collector-error.json')))
            self.assertTrue(all(result['native_continuity_passed'] for result in results))

    def test_provider_error_after_every_retry_holds_the_campaign(self):
        ScriptedResponses.fail_subject_requests = 10_000
        with tempfile.TemporaryDirectory() as temporary:
            root, reg = self.collect(temporary, 'off')
            completion = run.load(root / 'completion.json')
            self.assertEqual(completion['status'], 'provider_hold', completion)
            errors = list((root / 'natural').glob('*/trace/*.collector-error.json'))
            self.assertTrue(errors)
            self.assertEqual(run.load(errors[0])['transport_attempts'], 4)


if __name__ == '__main__':
    unittest.main()
