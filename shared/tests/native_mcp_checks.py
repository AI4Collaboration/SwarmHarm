"""Native call identity and asynchronous MCP arrival; no hosted inference."""
import json
import threading
import time
import unittest
from codex_session import CodexAgent


class NativeMcpChecks(unittest.TestCase):
    def agent(self):
        agent = object.__new__(CodexAgent)
        agent.lock = threading.RLock()
        agent.call_ready = threading.Condition(agent.lock)
        agent.calls = {}
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
