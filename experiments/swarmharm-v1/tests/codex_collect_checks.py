"""Subscription guards and offline integration with the pinned native Codex CLI."""

from contextlib import contextmanager

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import base64
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import export_atif
import launch
import run

C = run.codex_agent
MODEL = 'gpt-5.5'  # Recognized fixture metadata only; no hosted inference.


class CodexGuards(unittest.TestCase):
    def test_interrupted_rendering_preserves_execution_without_claiming_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'natural/actor';native=folder/'codex/native'
            session,turn='session-one','turn-one'
            system={'role':'system','content':json.dumps(C.SYSTEM_PROMPT)}
            plan={'type':'function_call','name':'update_plan','call_id':'plan-one',
                  'arguments':'{"plan":[{"step":"Confirm service","status":"in_progress"}]}'}
            business={'type':'function_call','name':'confirm_service','call_id':'business-one','arguments':'{}'}
            result={'status':'available'};output=json.dumps(result)
            plan_result={'type':'function_call_output','call_id':'plan-one','output':'Plan updated'}
            raw=[('rawResponseItem/completed',{'item':plan}),
                 ('rawResponseItem/completed',{'item':{**business,'namespace':'mcp__work'}}),
                 ('rawResponseItem/completed',{'item':plan_result}),
                 ('item/completed',{'item':{'type':'mcpToolCall','id':'business-one',
                    'server':'work','tool':'confirm_service','arguments':{},'status':'completed',
                    'result':{'content':[{'type':'text','text':output}]},'error':None}}),
                 ('rawResponseItem/completed',{'item':{'type':'function_call_output',
                    'call_id':'business-one','output':'aborted by user after 0.1s'}}),
                 ('turn/completed',{'turn':{'id':turn,'status':'interrupted'}})]
            for index,(method,params) in enumerate(raw,1):
                run.save(native/f'{index:06d}.json',{'direction':'server','message':{
                    'method':method,'params':{'threadId':session,'turnId':turn,**params}}})
            for name in ('catalog.json','tool-profile.json'):run.save(folder/'codex'/name,{'models':[]})
            harness={'kind':'codex','system_prompt':C.SYSTEM_PROMPT,'goal_mode':'off',
                     'request_count_scope':'observed native response groups'}
            run.save(root/'registration.json',{'harness':harness})
            run.save(folder/'result.json',{'status':'operator_interrupted','codex_session':{'session_id':session}})
            run.save(folder/'trace/0001.request.json',{'record_kind':'controller_projection',
                'model':MODEL,'input':[system],'tools':[], 'system_prompt_config':C.SYSTEM_PROMPT,
                'session_id':session,'native_turn_id':turn,'native_record':'native/000001.json','native_input_records':[]})
            run.save(folder/'trace/0001.response.json',{'model':MODEL,'status':'in_progress',
                'output':[plan,business],'session_id':session,'native_turn_id':turn,
                'native_record':'native/000003.json','native_output_records':['native/000001.json','native/000002.json']})
            run.save(folder/'trace/0001-tool-1.json',{'event_id':1,'call_id':'business-one',
                'name':'confirm_service','arguments':'{}','result':result})
            run.save(folder/'history.json',[system,plan,business,plan_result,
                {'type':'function_call_output','call_id':'business-one','output':output}])
            original=(native/'000005.json').read_bytes()
            export_atif.export_actor(root,'natural','actor')
            trajectory=run.load(folder/'agent/trajectory.json')
            step=next(step for step in trajectory['steps'] if step.get('tool_calls'))
            delivery=step['extra']['tool_result_delivery']['business-one']
            self.assertTrue(delivery['mcp_completion_verified'])
            self.assertFalse(delivery['rendered_result_verified'])
            self.assertFalse(delivery['sdk_delivery_verified'])
            self.assertTrue(delivery['native_turn_interrupted'])
            self.assertEqual(step['observation']['results'][-1]['content'],output)
            self.assertEqual(step['observation']['results'][-1]['extra'],{
                'content_source':'controller_execution','rendered_result_verified':False})
            self.assertEqual((native/'000005.json').read_bytes(),original)
            path=native/'000006.json';interrupted=path.read_bytes()
            value=run.load(path);value['message']['params']['turn']['status']='completed';run.save(path,value)
            with self.assertRaisesRegex(AssertionError,'rendered tool output differs'):
                export_atif.export_actor(root,'natural','actor')
            path.write_bytes(interrupted)

    def test_atif_preserves_non_object_arguments_as_explicit_raw_evidence(self):
        from harbor.models.trajectories.tool_call import ToolCall
        for raw in ('{','null','[]','"text"','42'):
            with self.subTest(arguments=raw):
                value=export_atif.atif_tool_call({'call_id':'rejected','name':'confirm_service','arguments':raw})
                validated=ToolCall.model_validate(value)
                self.assertEqual(validated.arguments,{})
                self.assertEqual(validated.extra['raw_arguments'],raw)
                self.assertFalse(validated.extra['arguments_valid_object'])
        value=export_atif.atif_tool_call({'call_id':'valid','name':'confirm_service','arguments':'{"tag":"a"}'})
        self.assertEqual(value['arguments'],{'tag':'a'})
        self.assertNotIn('extra',value)

    def test_unexpected_native_exit_unblocks_requests_and_reports_loss_of_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            events=C.new_queue()
            rpc=C.CodexRpc([sys.executable,'-c','pass'],env={},cwd=temporary,
                folder=Path(temporary)/'rpc',notification=lambda message,source:events.put(message))
            try:
                with self.assertRaisesRegex(RuntimeError,'connection closed'):
                    rpc.request('initialize',{},timeout=2)
                self.assertEqual(events.get(timeout=2)['method'],'transport/error')
            finally:rpc.close()

    def test_api_auth_routing_and_aliases_are_rejected_without_values(self):
        for name in C.CONFLICTING_ENV:
            with patch.dict(os.environ, {name: 'private-fixture-value'}, clear=True):
                with self.assertRaisesRegex(RuntimeError, name) as error:
                    C.subscription_env('/tmp/private-home')
                self.assertNotIn('private-fixture-value', str(error.exception))
        for model in ('openai/gpt-5.5', 'auto', 'latest', 'default', 'gpt-latest', ''):
            with self.assertRaises(ValueError):C.validate_model(model)
        with self.assertRaisesRegex(ValueError, 'goal mode off'):
            C.harness_registration('goal_command', MODEL)

    def test_access_snapshot_excludes_refresh_tokens_and_requires_sufficient_lifetime(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            def auth(expiry):
                payload = base64.urlsafe_b64encode(json.dumps({'exp': expiry}).encode()).decode().rstrip('=')
                return {'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
                    'last_refresh': datetime.now(timezone.utc).isoformat(),
                    'tokens': {'access_token': 'fixture.' + payload + '.signature',
                               'refresh_token': 'operator-refresh-only'}}
            original = auth(time.time() + 7200)
            (source / 'auth.json').write_text(json.dumps(original))
            with patch.dict(os.environ, {'CODEX_HOME': temporary}, clear=True):
                with C.isolated_home() as home:
                    saved = json.loads((home / 'auth.json').read_text())
                    self.assertEqual(saved['tokens']['refresh_token'], '')
                    self.assertEqual((home / 'auth.json').stat().st_mode & 0o777, 0o600)
                self.assertFalse(home.exists())
                self.assertEqual(json.loads((source / 'auth.json').read_text()), original)
                (source / 'auth.json').write_text(json.dumps(auth(time.time() + 60)))
                with self.assertRaisesRegex(RuntimeError, 'Refresh'):
                    with C.isolated_home():pass
                original['auth_mode'] = 'apikey'
                (source / 'auth.json').write_text(json.dumps(original))
                with self.assertRaisesRegex(RuntimeError, 'not API-key'):
                    with C.isolated_home():pass

    def test_profile_preserves_all_native_instruction_fields(self):
        catalog = {'models': [{'base_instructions': 'Native fixture instructions',
            'model_messages': {'instructions_template': 'Native fixture template'},
            'apply_patch_tool_type': 'freeform', 'input_modalities': ['text', 'image'],
            'supports_parallel_tool_calls': True}]}
        changed = C.catalog_profile(catalog)
        for field in ('base_instructions', 'model_messages'):
            self.assertEqual(changed['models'][0][field], catalog['models'][0][field])
        self.assertFalse(changed['models'][0]['supports_parallel_tool_calls'])
        self.assertIsNone(changed['models'][0]['apply_patch_tool_type'])


class ScriptedResponses(BaseHTTPRequestHandler):
    def log_message(self, *unused):pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.server.capture_lock:
            self.server.captures.append(request)
            index = len(self.server.captures)
        latest = max(i for i, item in enumerate(request['input']) if item.get('role') == 'user')
        text = '\n'.join(p.get('text', '') for p in request['input'][latest]['content'])
        returned = any(item['type'] == 'function_call_output' for item in request['input'][latest + 1:])
        recovering = (getattr(self.server, 'invalid_arguments', False) and
            sum(item['type']=='function_call_output' for item in request['input'][latest+1:])==1)
        if getattr(self.server, 'goal_fixture', False) and index == 3:
            items = [{'type':'function_call', 'name':'update_goal', 'call_id':f'goal-{index}',
                      'arguments':json.dumps({'status':'complete'})}]
        elif (returned and not recovering) or text.startswith('Baseline'):
            items = [{'type': 'message', 'id': f'msg-{index}', 'role': 'assistant',
                'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': 'Fixture complete.'}]}]
        else:
            name = ('close_record' if text.startswith('Close fixture') else
                    'view_image' if text.startswith('Image fixture') else
                    'confirm_service' if text.startswith('Service fixture') or 'confirm_service' in text else 'bash')
            args = {'command': 'pwd'} if name == 'bash' else {'path': '/operator/fixture.png'} if name == 'view_image' else {}
            items = [{'type': 'function_call', 'name': name, 'call_id': f'call-{index}',
                      'arguments': json.dumps(args),
                      **({'namespace': 'mcp__work'} if name != 'view_image' else {})}]
            if getattr(self.server, 'multiple', False):
                items = [{**items[0], 'call_id': f'call-{index}-{tag}',
                          'arguments': json.dumps({'tag': tag})} for tag in ('a', 'b')]
            if getattr(self.server, 'invalid_arguments', False) and not recovering:
                items[0]['arguments']='{'
            if getattr(self.server, 'mixed_tools', False):
                items.insert(0, {'type':'function_call','name':getattr(self.server,'auxiliary_tool','update_plan'),
                    'call_id':f'plan-{index}','arguments':json.dumps({
                        'plan':[{'step':'Confirm service status','status':'in_progress'}]})})
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        events = [{'type': 'response.created', 'response': {'id': f'resp-{index}'}}]
        events += [{'type': 'response.output_item.done', 'output_index': i, 'item': item}
                   for i, item in enumerate(items)]
        events.append({'type': 'response.completed', 'response': {'id': f'resp-{index}',
            'status': 'completed', 'model': MODEL, 'output': items,
            'usage': {'input_tokens': 10, 'output_tokens': 3, 'total_tokens': 13}}})
        for event in events:
            self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()


@unittest.skipUnless(shutil.which('codex'), 'Pinned Codex CLI required for native offline checks')
class NativeCodex(unittest.TestCase):
    @contextmanager
    def fixture(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), ScriptedResponses)
        server.captures, server.capture_lock = [], threading.Lock()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original_config = C.write_config
        @contextmanager
        def home():
            with tempfile.TemporaryDirectory(prefix='codex-fixture-', dir='/tmp') as temporary:
                yield Path(temporary)
        def config(folder, *args):
            original_config(folder, *args)
            path = folder / 'config.toml'
            value = path.read_text().replace('model_provider="openai"', 'model_provider="fixture"')
            value = value.replace('forced_login_method="chatgpt"\n', '')
            value += ('\n[model_providers.fixture]\nname="Offline protocol fixture"\n'
                f'base_url="http://127.0.0.1:{server.server_port}/v1"\nwire_api="responses"\n'
                'requires_openai_auth=false\nsupports_websockets=false\n'
                'request_max_retries=0\nstream_max_retries=0\n')
            path.write_text(value)
        try:
            with ExitStack() as patches:
                clean = {key: value for key, value in os.environ.items() if key not in C.CONFLICTING_ENV}
                patches.enter_context(patch.dict(os.environ, clean, clear=True))
                patches.enter_context(patch.object(C, 'isolated_home', home))
                patches.enter_context(patch.object(C, 'write_config', config))
                patches.enter_context(patch.object(C, 'check_subscription', return_value={'authentication': 'offline-fixture'}))
                yield server
        finally:
            server.shutdown()
            server.server_close()

    def drain(self, agent, events, folder):
        result = None;tool_counts = {}
        while result is None:
            _, message = events.get(timeout=30)
            kind, turn = message['type'], message.get('turn', 0)
            trace = folder / 'trace';trace.mkdir(exist_ok=True)
            if kind == 'request':
                run.save(trace / f'{turn:04d}.request.json', message['payload'])
            elif kind in ('response_update', 'provider_response'):
                value = message['response'] if kind == 'response_update' else message['event']['response']
                run.save(trace / f'{turn:04d}.response.json', value)
                run.save(folder / 'history.json', message['history'])
            elif kind == 'tool_call':
                value = {'status': 'available'}
                if 'tag' in message['arguments']:value['tag']=message['arguments']['tag']
                tool_counts[turn]=tool_counts.get(turn,0)+1
                run.save(trace / f'{turn:04d}-tool-{tool_counts[turn]}.json', {'call_id': message['call_id'],
                    'name': message['name'], 'arguments': json.dumps(message['arguments']),
                    'event_id': turn*10+tool_counts[turn], 'result': value})
                agent.reply(message['id'], output=json.dumps(value, ensure_ascii=False))
            elif kind == 'settled':result = message
            elif kind in ('fatal', 'exited'):self.fail(str(message))
        return result

    def export_trace(self, root, ready):
        folder=root/'natural/actor'
        run.save(root/'registration.json',{'harness':{
            'kind':'codex','system_prompt':C.SYSTEM_PROMPT,'goal_mode':'off',
            'request_count_scope':'observed native response groups'}})
        run.save(folder/'result.json',{'status':'collected','codex_session':ready})
        result=export_atif.export_actor(root,'natural','actor')
        return result,run.load(folder/'agent/trajectory.json')

    def test_native_roundtrip_phase2_reload_and_atif_keep_one_thread(self):
        with self.fixture() as server, tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);folder = root / 'natural' / 'actor';folder.mkdir(parents=True)
            events = C.new_queue()
            tools = [{'type': 'function', 'name': name, 'description': 'Read or file the service record.',
                'parameters': {'type': 'object', 'properties': {}}} for name in ('confirm_service', 'close_record')]
            agent = C.CodexAgent('actor', events, folder=folder / 'codex', model=MODEL,
                thinking_level='high', tools=tools, active_tools=['confirm_service'], goal_mode='off',
                job_context='Legacy generic prompt must not be appended.')
            try:
                ready = C.wait_ready(events, ['actor'])['actor']
                agent.prompt('Service fixture request.')
                self.drain(agent, events, folder)
                agent.set_tools(['confirm_service', 'close_record'])
                agent.prompt('Close fixture record.')
                self.drain(agent, events, folder)
            finally:agent.close()
            result,trajectory = self.export_trace(root,ready)
            self.assertEqual(result['requests'], 4)
            self.assertTrue(trajectory['extra']['phase2_tools_seen'])
            self.assertFalse(trajectory['extra']['provider_context_continuity_verified'])
            delivery = [value for step in trajectory['steps'] for value in step.get('extra', {}).get('tool_result_delivery', {}).values()]
            self.assertEqual(len(delivery), 2)
            self.assertTrue(all(value['sdk_delivery_verified'] for value in delivery))
            initial = next(tool for tool in server.captures[0]['tools'] if tool['type'] == 'namespace')
            later = next(tool for tool in server.captures[2]['tools'] if tool['type'] == 'namespace')
            self.assertEqual([t['name'] for t in initial['tools']], ['confirm_service'])
            self.assertEqual({t['name'] for t in later['tools']}, {'confirm_service', 'close_record'})
            self.assertTrue(all(request['parallel_tool_calls'] is False for request in server.captures))
            self.assertEqual({tool['name'] for tool in server.captures[0]['tools'] if tool['type']=='function'}, set(C.NATIVE_TOOLS))
            self.assertNotIn(str(root), json.dumps(server.captures))
            self.assertNotIn('Legacy generic prompt', json.dumps(server.captures))
            path = folder / 'trace/0001.response.json';original = path.read_bytes()
            value = run.load(path);value['output'][0]['arguments'] = '{"changed":true}'
            run.save(path, value)
            with self.assertRaisesRegex(AssertionError, 'native output'):
                export_atif.codex_native_evidence(folder, sorted((folder / 'trace').glob('????.request.json')))
            path.write_bytes(original)

    def test_calls_from_one_native_response_keep_one_causal_step(self):
        with self.fixture() as server, tempfile.TemporaryDirectory() as temporary:
            server.multiple = True
            folder = Path(temporary) / 'actor';events = C.new_queue()
            tool = {'type': 'function', 'name': 'confirm_service', 'description': 'Read service status.',
                    'parameters': {'type': 'object', 'properties': {'tag': {'type': 'string'}}}}
            agent = C.CodexAgent('actor', events, folder=folder / 'codex', model=MODEL,
                thinking_level='high', tools=[tool], active_tools=['confirm_service'], goal_mode='off')
            try:
                C.wait_ready(events, ['actor'])
                agent.prompt('Service fixture with two records.')
                self.drain(agent, events, folder)
            finally:agent.close()
            self.assertEqual(len(server.captures), 2)
            self.assertEqual(len(list((folder/'trace').glob('????.request.json'))), 2)
            self.assertEqual(len(run.load(folder/'trace/0001.response.json')['output']), 2)
            self.assertEqual(len(list((folder/'trace').glob('0001-tool-*.json'))), 2)
            self.assertFalse(list((folder/'trace').glob('0002-tool-*.json')))

    def test_native_instructions_match_baseline_and_host_image_tool_is_inert(self):
        with self.fixture() as server, tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def one(label):
                events = C.new_queue()
                agent = C.CodexAgent('actor', events, folder=root / label / 'codex', model=MODEL,
                    thinking_level='high', tools=[], active_tools=[], goal_mode='off')
                try:
                    C.wait_ready(events, ['actor'])
                    agent.prompt(label + ' fixture request.')
                    self.drain(agent, events, root / label)
                finally:agent.close()
            with patch.object(C, 'catalog_profile', side_effect=deepcopy):one('Baseline')
            baseline = server.captures[-1]['instructions']
            one('Image')
            self.assertEqual(server.captures[-1]['instructions'], baseline)
            outputs = [item['output'] for item in server.captures[-1]['input'] if item['type'] == 'function_call_output']
            self.assertEqual(outputs, ['view_image is not allowed because you do not support image inputs'])

    def test_native_argument_error_can_be_corrected_before_business_execution(self):
        with self.fixture() as server, tempfile.TemporaryDirectory() as temporary:
            server.invalid_arguments = True
            root=Path(temporary);folder=root/'natural/actor';events=C.new_queue()
            tool={'type':'function','name':'confirm_service','description':'Read service status.',
                  'parameters':{'type':'object','properties':{}}}
            agent=C.CodexAgent('actor',events,folder=folder/'codex',model=MODEL,
                thinking_level='high',tools=[tool],active_tools=['confirm_service'],goal_mode='off')
            try:
                ready=C.wait_ready(events,['actor'])['actor'];agent.prompt('Service fixture request.')
                self.drain(agent,events,folder)
            finally:agent.close()
            self.assertFalse(list((folder/'trace').glob('0001-tool-*.json')))
            self.assertEqual(len(list((folder/'trace').glob('0002-tool-*.json'))),1)
            self.assertEqual(len(server.captures),3)
            outputs=[item['output'] for item in server.captures[-1]['input'] if item['type']=='function_call_output']
            self.assertEqual(len(outputs),2)
            self.assertIn('parsing',outputs[0].lower())
            response=folder/'trace/0001.response.json';original=response.read_bytes()
            _,trajectory=self.export_trace(root,ready)
            rejected=next(call for step in trajectory['steps'] for call in step.get('tool_calls',[])
                if call['tool_call_id']==run.load(response)['output'][0]['call_id'])
            self.assertEqual(rejected['arguments'],{})
            self.assertEqual(rejected['extra']['raw_arguments'],'{')
            self.assertFalse(rejected['extra']['arguments_valid_object'])
            self.assertEqual(response.read_bytes(),original)

    def test_mixed_native_and_business_results_export_in_native_order(self):
        with self.fixture() as server,tempfile.TemporaryDirectory() as temporary:
            server.mixed_tools=True
            root=Path(temporary);folder=root/'natural/actor';events=C.new_queue()
            tool={'type':'function','name':'confirm_service','description':'Read service status.',
                  'parameters':{'type':'object','properties':{}}}
            agent=C.CodexAgent('actor',events,folder=folder/'codex',model=MODEL,
                thinking_level='high',tools=[tool],active_tools=['confirm_service'],goal_mode='off')
            try:
                ready=C.wait_ready(events,['actor'])['actor'];agent.prompt('Service fixture request.')
                self.drain(agent,events,folder)
            finally:agent.close()
            _,trajectory=self.export_trace(root,ready)
            step=next(step for step in trajectory['steps'] if step.get('tool_calls'))
            incoming=run.load(folder/'trace/0002.request.json')['input']
            order=[item['call_id'] for item in incoming if item.get('type')=='function_call_output']
            self.assertEqual(order,['plan-1','call-1'])
            self.assertEqual([item['source_call_id'] for item in step['observation']['results']],order)
            self.assertEqual(step['extra']['controller_execution_order'],['call-1'])
            paths=[folder/'trace/0002.request.json',folder/'history.json']
            originals=[path.read_bytes() for path in paths]
            for change in ('content','order'):
                with self.subTest(tamper=change):
                    try:
                        for path in paths:
                            value=run.load(path);items=value['input'] if isinstance(value,dict) else value
                            indices=[i for i,item in enumerate(items) if item.get('type')=='function_call_output']
                            if change=='content':items[indices[0]]['output']='forged native result'
                            else:items[indices[0]],items[indices[1]]=items[indices[1]],items[indices[0]]
                            run.save(path,value)
                        with self.assertRaisesRegex(AssertionError,'native tool result'):
                            export_atif.export_actor(root,'natural','actor')
                    finally:
                        for path,original in zip(paths,originals):path.write_bytes(original)

    def test_prepare_collect_and_native_export_without_api_routing(self):
        with self.fixture(), tempfile.TemporaryDirectory() as temporary, ExitStack() as patches:
            root = Path(temporary) / 'rollout'
            registration = run.REGISTRATIONS / ('test-codex-' + Path(temporary).name)
            self.addCleanup(shutil.rmtree, registration, True)
            patches.enter_context(patch.object(run, 'MODELS', {'codex': MODEL}))
            patches.enter_context(patch.object(run, 'UPSTREAM_MODELS', {'codex': MODEL}))
            patches.enter_context(patch.object(C, 'subscription_catalog', return_value={
                'authentication': 'offline-fixture', 'model': MODEL, 'effort': 'high', 'inference_calls': 0}))
            routes = patches.enter_context(patch.object(run, 'verify_routes', side_effect=AssertionError('No API route')))
            run.prepare(root, registration, None, run_controls=False, harness_kind='codex')
            reg = run.load(root / 'registration.json')
            self.assertIsNone(reg['api_base'])
            self.assertEqual(reg['harness']['authentication'], 'chatgpt-subscription')
            self.assertTrue(all('experiments/runtime/' + name in reg['code_hashes'] for name in
                ('codex_agent.py', 'codex_rpc.py', 'codex_mcp.py', 'codex_session.py', 'codex_evidence.py')))
            reg['budget'].update(max_batch_seconds=25, max_actor_seconds=25)
            if reg.get('source_publication'):reg['source_publication']['after_start_seconds'] = 1
            run.save(root / 'registration.json', reg)
            run.save(root / 'registration-seal.json', {'sha256': run.sha(root / 'registration.json')})
            patches.enter_context(patch.object(run, 'verify_collection_freeze'))
            patches.enter_context(patch.object(run, 'AXONHUB_KEY_FILE', None))
            run.collect(root, registration)
            routes.assert_not_called()
            self.assertIn(run.load(root / 'completion.json')['status'], {'collected', 'collected_with_limits'})
            self.assertEqual(len(export_atif.export(root)), 4)


if __name__ == '__main__':unittest.main()
