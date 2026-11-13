"""Native call identity and asynchronous MCP arrival; no hosted inference."""
import json
import io
from contextlib import redirect_stdout
import threading
import time
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import codex_mcp
from codex_session import CodexAgent


class NativeMcpChecks(unittest.TestCase):
    def agent(self):
        agent = object.__new__(CodexAgent)
        agent.lock = threading.RLock()
        agent.call_ready = threading.Condition(agent.lock)
        agent.calls = {}
        agent.active_tools = ['read_delivery_discussion']
        agent.stopping = False
        agent.thread_id = 'thread'
        return agent

    def call(self, channel='public'):
        return {'business': True, 'claimed': False,
                'item': {'name': 'read_delivery_discussion',
                         'arguments': json.dumps({'channel': channel, 'after_reference': None, 'limit': 100})}}

    def params(self):
        return {'name': 'read_delivery_discussion',
                'arguments': {'channel': 'public', 'after_reference': None, 'limit': 100},
                '_meta': {'callId': 'native-call', 'threadId': 'thread'}}

    def test_execution_waits_for_exact_native_event_on_independent_pipe(self):
        agent = self.agent(); results = []
        def execute():
            with agent.lock:results.append(agent._match_call(self.params()))
        worker = threading.Thread(target=execute); worker.start()
        time.sleep(0.03)
        self.assertTrue(worker.is_alive())
        with agent.call_ready:
            agent.calls['native-call'] = self.call()
            agent.call_ready.notify_all()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0][0], 'native-call')

    def test_identical_arguments_bind_by_native_id(self):
        agent = self.agent();agent.calls = {'other-call': self.call(), 'native-call': self.call()}
        with agent.lock:self.assertEqual(agent._match_call(self.params())[0], 'native-call')

    def test_wrong_arguments_thread_or_missing_identity_cannot_bind(self):
        agent = self.agent();agent.calls['native-call'] = self.call('private')
        with agent.lock:
            with self.assertRaisesRegex(RuntimeError, 'differs'):agent._match_call(self.params())
            params = self.params();params['_meta']['threadId'] = 'other'
            with self.assertRaisesRegex(RuntimeError, 'different native thread'):agent._match_call(params)
            agent.calls.clear()
            with self.assertRaisesRegex(RuntimeError, 'no matching'):agent._match_call(self.params(), timeout=0.01)

    def test_inactive_native_call_cannot_match_controller_execution(self):
        agent = self.agent(); agent.calls['native-call'] = self.call()
        agent.active_tools = []
        with agent.lock:
            with self.assertRaisesRegex(RuntimeError, 'inactive tool'):
                agent._match_call(self.params())

    def test_proxy_rejects_inactive_tool_before_connecting_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            definitions = Path(directory) / 'tools.json'
            definitions.write_text(json.dumps([{'name': 'read_delivery_discussion'}]))
            request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                       'params': {'name': 'not_active', 'arguments': {}}}
            output = io.StringIO()
            with patch('sys.stdin', io.StringIO(json.dumps(request) + '\n')), \
                    patch('codex_mcp.socket.socket') as socket_factory, redirect_stdout(output):
                codex_mcp.serve(definitions, '/not/a/real/socket')
            socket_factory.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())['error'],
                             {'code': -32602, 'message': 'Tool is not active'})
