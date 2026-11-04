"""Native Pi request admission and exact Abliteration provenance; no hosted calls."""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import run
from tests.pi_collect_checks import ScriptedResponses


class PiAdmissionChecks(unittest.TestCase):
    def test_fifo_cancel_does_not_release_an_active_request_before_it_ends(self):
        gate=run.pi_agent.InferenceGate(1)
        first,second,third=object(),object(),object()
        self.assertTrue(gate.acquire(first))
        with ThreadPoolExecutor(max_workers=2) as pool:
            b=pool.submit(gate.acquire,second)
            while second not in gate.pending:time.sleep(.001)
            c=pool.submit(gate.acquire,third)
            while third not in gate.pending:time.sleep(.001)
            gate.cancel(second)
            self.assertFalse(b.result(timeout=2))
            gate.cancel(first)
            self.assertFalse(c.done())
            gate.release(first)
            self.assertTrue(c.result(timeout=2))
            gate.release(third)
        self.assertFalse(gate.active)
        self.assertFalse(gate.pending)

    def test_four_native_sessions_serialize_requests_and_keep_tool_round_trips(self):
        class Server(ScriptedResponses):
            requests=[]
            active=0
            peak=0
            lock=threading.Lock()

            def do_POST(self):
                with type(self).lock:
                    type(self).active+=1
                    type(self).peak=max(type(self).peak,type(self).active)
                try:
                    time.sleep(.04)
                    return super().do_POST()
                finally:
                    with type(self).lock:type(self).active-=1

        server=ThreadingHTTPServer(('127.0.0.1',0),Server)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        gate=run.pi_agent.InferenceGate(1)
        events=run.pi_agent.new_queue()
        tool={'type':'function','name':'confirm_service','description':'Return service status.',
            'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False},'strict':True}
        agents={}
        with tempfile.TemporaryDirectory() as temporary:
            try:
                for actor in ('a','b','c','d'):
                    agents[actor]=run.pi_agent.PiAgent(actor,events,
                        folder=Path(temporary)/actor,model='offline-model',
                        api_base=f'http://127.0.0.1:{server.server_port}/v1',api_key='offline-key',
                        thinking_level='high',max_output_tokens=1024,context_window=1000000,
                        request_timeout_ms=10000,tools=[tool],active_tools=['confirm_service'],
                        job_context=None,goal_mode='off',inference_gate=gate)
                run.pi_agent.wait_ready(events,agents)
                # All four contexts exist before any request is admitted.
                self.assertEqual(Server.requests,[])
                for agent in agents.values():agent.prompt('Check service availability using confirm_service.')
                settled=set();calls=[]
                while len(settled)<4:
                    actor,message=events.get(timeout=30)
                    if message['type']=='tool_call':
                        calls.append(actor);agents[actor].reply(message['id'],output='{"status":"available"}')
                    elif message['type']=='settled':
                        self.assertFalse(message.get('error_message'))
                        self.assertIn('available',message['text']);settled.add(actor)
                    elif message['type'] in ('fatal','exited'):
                        self.fail(str(message))
                self.assertEqual(Server.peak,1)
                self.assertEqual(sorted(calls),['a','b','c','d'])
                self.assertEqual(len(Server.requests),8)
                for actor in agents:
                    self.assertEqual(len(list((Path(temporary)/actor/'session').glob('*.jsonl'))),1)
            finally:
                for agent in agents.values():agent.close()
                server.shutdown();server.server_close()
        self.assertFalse(gate.active)
        self.assertFalse(gate.pending)

    def test_abliteration_uses_vendor_listing_without_a_stock_glm_substitution(self):
        exact='abliterated-model-large-v2'
        with patch.object(run,'MODELS',{'glm':exact}),patch.object(run,'UPSTREAM_MODELS',{'glm':exact}),\
                patch.object(run,'abliteration_model_listing',return_value={'model_found':True}) as vendor,\
                patch.object(run,'catalog',return_value={'model_found':True}) as gateway:
            routes=run.verify_routes(Path('/outside/key'))
        vendor.assert_called_once_with(exact)
        gateway.assert_called_once_with(run.AXONHUB_CATALOG,exact,Path('/outside/key'))
        self.assertIsNone(routes['openrouter_catalog_endpoint'])
        with patch.object(run,'MODELS',{'glm':'z-ai/glm-5.3'}),patch.object(run,'UPSTREAM_MODELS',{'glm':exact}):
            with self.assertRaisesRegex(ValueError,'exact upstream identity'):
                run.verify_routes(Path('/outside/key'))

    def test_vendor_listing_does_not_accept_a_longer_model_name(self):
        import io
        class Response(io.BytesIO):status=200
        for body,expected in [(b'abliterated-model-large-v2',True),
                              (b'abliterated-model-large-v2-flash',False)]:
            with patch.object(run.guardrails,'open_url',return_value=Response(body)):
                self.assertEqual(run.abliteration_model_listing('abliterated-model-large-v2')['model_found'],expected)
