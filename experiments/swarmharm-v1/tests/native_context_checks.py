"""Pinned native context protocol checks against a local scripted endpoint."""
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import codex_gateway
from codex_agent import wait_ready
from codex_session import CodexAgent
from codex_context import POLICY, ContextLifecycle, validate_checkpoints
from codex_evidence import native_evidence


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append({'path': self.path, 'body': request})
        n = len(self.server.requests)
        if n > 6 or 'compact' in self.path:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"offline fixture boundary"}}')
            return
        compact = any(x['type'] == 'compaction_trigger' for x in request['input'])
        if compact:
            items = [{'type': 'compaction', 'encrypted_content': f'opaque-fixture-{n}'}]
        elif n < 5:
            items = [{'type': 'function_call', 'name': 'confirm_service',
                      'namespace': 'mcp__work', 'call_id': f'fixture-call-{n}', 'arguments': '{}'}]
        else:
            items = [{'type': 'message', 'id': f'msg-{n}', 'role': 'assistant',
                      'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': 'Fixture complete.'}]}]
        events = [{'type': 'response.created', 'response': {'id': f'resp-{n}'}}]
        events.extend({'type': 'response.output_item.done', 'output_index': i, 'item': x}
                      for i, x in enumerate(items))
        events.append({'type': 'response.completed', 'response': {
            'id': f'resp-{n}', 'status': 'completed', 'model': request['model'], 'output': items,
            'usage': {'input_tokens': 10 if compact or n == 5 else 300000, 'output_tokens': 3, 'total_tokens': 13 if compact or n == 5 else 300003}}})
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        try:
            for event in events:
                self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class NativeContextChecks(unittest.TestCase):
    def test_matched_eight_member_context_lifecycles(self):
        from swarmform.research_preview import preview
        before = preview(responsive=True)
        after = preview(context_maintenance=True)
        self.assertEqual(before['conditions'], after['conditions'])
        self.assertEqual(before['automatic_notices'], after['automatic_notices'])
        for condition in ('intended', 'unintended'):
            for actor, texts in after['conditions'][condition]['input']['prompts'].items():
                with self.subTest(condition=condition, actor=actor):
                    self.check_native_remote_compaction_protocol(condition+'-'+actor, '\n\n'.join(texts))

    def check_native_remote_compaction_protocol(self, name, prompt):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.environ.get('SWARMHARM_CONTEXT_WITNESS', temporary)) / name
            folder = root/'natural/Fixture'
            folder.mkdir(parents=True, exist_ok=True)
            (folder/'trace').mkdir()
            harness = codex_gateway.harness_registration('off', 'openai/gpt-6.1-sol', context_policy=POLICY)
            (root/'registration.json').write_text(json.dumps({'harness': harness}))
            server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
            server.requests = []
            threading.Thread(target=server.serve_forever, daemon=True).start()
            original = codex_gateway.write_config
            def local_config(home, *args, **kwargs):
                original(home, *args, **kwargs)
                p = home / 'config.toml'
                text = p.read_text().replace(codex_gateway.AXONHUB_BASE,
                    f'http://127.0.0.1:{server.server_port}/v1')
                text = text.replace('requires_openai_auth=false',
                    'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0')
                p.write_text(text)
            events = queue.Queue()
            observed = []
            agent = None
            try:
                with patch.object(codex_gateway, 'write_config', local_config):
                    agent = CodexAgent('Fixture', events, folder=folder / 'codex',
                        model='openai/gpt-6.1-sol', thinking_level='high', registered_harness=harness,
                        tools=[{'type': 'function', 'name': 'confirm_service', 'description': 'Read fixture status.',
                            'parameters': {'type': 'object', 'properties': {}}}],
                        active_tools=['confirm_service'], goal_mode='off',
                        api_base=codex_gateway.AXONHUB_BASE, api_key='offline-fixture', request_timeout_ms=30000)
                    wait_ready(events, ['Fixture'])
                    agent.prompt(prompt)
                    deadline = time.monotonic() + 40
                    while time.monotonic() < deadline:
                        _, event = events.get(timeout=10)
                        observed.append(event)
                        turn = event.get('turn', 0)
                        if event['type'] == 'request':
                            (folder/'trace'/f'{turn:04d}.request.json').write_text(json.dumps(event['payload']))
                        if event['type'] in ('response_update', 'provider_response'):
                            value = event['response'] if event['type'] == 'response_update' else event['event']['response']
                            (folder/'trace'/f'{turn:04d}.response.json').write_text(json.dumps(value))
                            (folder/'history.json').write_text(json.dumps(event['history']))
                        if event['type'] == 'tool_call':
                            (folder/'trace'/f'{turn:04d}-tool-0001.json').write_text(json.dumps({
                                'call_id': event['call_id'], 'name': 'confirm_service', 'arguments': '{}',
                                'result': {'status': 'available'}}))
                            agent.reply(event['id'], output=json.dumps({'status': 'available'}))
                        if event['type'] in ('fatal', 'settled', 'exited'):
                            break
            finally:
                if agent:
                    agent.close()
                server.shutdown()
                server.server_close()
                (folder / 'requests.json').write_text(json.dumps(server.requests, indent=2) + '\n')
                (folder / 'events.json').write_text(json.dumps(observed, indent=2) + '\n')
            self.assertTrue(server.requests)
            self.assertEqual(observed[-1]['type'], 'settled', observed[-1])
            self.assertEqual(agent.turn, 3)
            self.assertEqual(agent.context.epoch, 2)
            self.assertEqual([e['payload']['context_epoch'] for e in observed if e['type']=='request'], [0, 1, 2])
            self.assertEqual(sum(e['usage']['input_tokens']+e['usage']['output_tokens'] for e in observed
                                 if e['type']=='context_usage'), 26)
            self.assertEqual(len([e for e in observed if e['type']=='provider_response']), 3)
            validate_checkpoints(folder/'codex/session.jsonl', 2)
            (folder/'result.json').write_text(json.dumps({'codex_session': {'session_id': agent.thread_id}}))
            seals, delivery = native_evidence(folder, sorted((folder/'trace').glob('*.request.json')))
            self.assertTrue(seals)
            self.assertTrue(all(row['sdk_delivery_verified'] for row in delivery.values()))
            for index in (1, 3):
                self.assertEqual(server.requests[index]['body']['input'][-1], {'type':'compaction_trigger'})
            for index in (2, 4):
                items=server.requests[index]['body']['input']
                self.assertEqual(len([x for x in items if x['type']=='compaction']), 1)
                self.assertNotIn('Another language model started', json.dumps(items))
                self.assertNotIn('CONTEXT CHECKPOINT COMPACTION', json.dumps(items))

    def test_lifecycle_rejects_missing_usage_and_text_handoff(self):
        context=ContextLifecycle()
        start={'method':'item/started','params':{'item':{'type':'contextCompaction','id':'c'}}}
        context.observe(start,'native/1')
        with self.assertRaisesRegex(ValueError,'Missing context maintenance usage'):
            context.observe({'method':'item/completed','params':start['params']},'native/2')
        with self.assertRaisesRegex(ValueError,'Research event'):
            context.observe({'method':'rawResponseItem/completed','params':{'item':{'type':'message'}}},'native/3')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'session.jsonl'
            p.write_text(json.dumps({'type':'compacted','payload':{'message':'Another language model'}}))
            with self.assertRaisesRegex(ValueError,'Textual context handoff'):
                validate_checkpoints(p,1)

    def test_maintenance_spends_existing_token_budget_without_fake_research_turn(self):
        from swarmform.structure_collection import StructureCollection
        from swarmform.collection import Collection
        with tempfile.TemporaryDirectory() as d, patch.object(Collection, 'handle'):
            collection=StructureCollection.__new__(StructureCollection)
            collection.root=Path(d);collection.publications=None
            collection.states={'A':{}};collection.usage={};collection.maintenance_usage={}
            collection.stopping=threading.Event()
            collection.reg={'budget':{'max_observed_tokens_per_agent':100,'max_responses_per_agent':10}}
            collection.handle('A', {'type':'provider_response','event':{'response':{
                'id':'research','usage':{'input_tokens':70,'output_tokens':10}}}}, None)
            with self.assertRaisesRegex(RuntimeError,'resource budget reached'):
                collection.handle('A', {'type':'context_usage','id':'maintenance',
                    'usage':{'input_tokens':20,'output_tokens':1}}, None)
            self.assertEqual(collection.states['A']['observed_tokens'],101)
            self.assertEqual(collection.states['A']['observed_research_responses'],1)
            self.assertEqual(collection.states['A']['context_responses'],1)


            collection.stopping.set()
            first_stop=collection.budget_stop
            collection.events=queue.Queue()
            collection.events.put(('A', {'type':'context_usage','id':'late-maintenance',
                'usage':{'input_tokens':20,'output_tokens':1}}))
            collection.drain_terminal_events(None)
            self.assertEqual(collection.states['A']['observed_tokens'],122)
            self.assertEqual(collection.states['A']['context_responses'],2)
            self.assertEqual(collection.budget_stop,first_stop)

    def test_planned_close_during_maintenance_retains_censoring_without_new_failure(self):
        with tempfile.TemporaryDirectory() as d, patch('threading.Thread.start'):
            agent=CodexAgent('A',queue.Queue(),folder=d,model='openai/gpt-6.1-sol',
                thinking_level='high',tools=[],active_tools=[],goal_mode='off',
                api_base=codex_gateway.AXONHUB_BASE,api_key='offline-fixture',
                registered_harness={'context_policy':POLICY})
            agent.thread_id='thread';agent.native_turn='turn';agent.active=True
            agent.last_progress=12
            agent._notification({'method':'item/started','params':{'item':{
                'type':'contextCompaction','id':'c'}}},'native/1')
            agent._notification({'method':'thread/tokenUsage/updated','params':{
                'tokenUsage':{'last':{'totalTokens':123}}}},'native/2')
            self.assertEqual(agent.last_progress,12)
            agent.stopping=True
            agent._notification({'method':'turn/completed','params':{
                'turn':{'id':'turn','status':'interrupted'}}},'native/3')
            self.assertFalse(agent.failed)
            self.assertFalse(agent.active)
            self.assertEqual(agent.turn,0)
            self.assertEqual(agent.context.epoch,0)
            self.assertEqual(len(agent.context.interrupted),1)
            with self.assertRaisesRegex(ValueError,'resumed after interrupted'):
                agent.context.observe({'method':'turn/started'},'native/4')
