"""Native Codex/AxonHub adapter checks using a local protocol fixture only."""
import json
import queue
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import run
import codex_gateway


class NativeGatewayChecks(unittest.TestCase):
    def test_codex_config_uses_exact_gateway_model_and_keeps_native_instructions(self):
        model='openai/gpt-5.6-sol'
        catalog={'models':[{'slug':'gpt-5.6-sol','base_instructions':'native instructions'}]}
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            codex_gateway.write_config(home,home,home/'tools.json',home/'call.sock',model,'high',catalog)
            config=tomllib.loads((home/'config.toml').read_text())
            self.assertEqual(config['model'],model)
            self.assertEqual(config['model_provider'],'axonhub')
            self.assertEqual(config['model_providers']['axonhub']['base_url'],codex_gateway.AXONHUB_BASE)
            self.assertFalse(config['model_providers']['axonhub']['requires_openai_auth'])
            self.assertNotIn('forced_login_method',config)
            row=json.loads((home/'catalog.json').read_text())['models'][0]
            self.assertEqual(row['slug'],model)
            self.assertEqual(row['base_instructions'],'native instructions')
            self.assertEqual(catalog['models'][0]['slug'],'gpt-5.6-sol')


    def test_gateway_environment_does_not_inherit_provider_or_subscription_auth(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'host-secret','CODEX_AUTH_JSON':'host-login'}):
            env=codex_gateway.gateway_env('/tmp/isolated-test',codex_gateway.AXONHUB_BASE,'fixture-key')
        self.assertNotIn('OPENAI_API_KEY',env)
        self.assertNotIn('CODEX_AUTH_JSON',env)
        self.assertEqual(env['SWARMHARM_AXONHUB_KEY'],'fixture-key')
        with self.assertRaises(ValueError):
            codex_gateway.gateway_env('/tmp/isolated-test','https://other.example/v1','fixture-key')


    def test_current_codex_mcp_blocks_reject_extra_or_changed_envelopes(self):
        from codex_evidence import mcp_output_text
        output=[{'type':'input_text','text':'Wall time: 0.0001 seconds\nOutput:'},
                {'type':'input_text','text':'{"status":"available"}'}]
        self.assertEqual(mcp_output_text(output),output[1]['text'])
        for bad in (output+[output[1]], [{'type':'input_text','text':'truncated'},output[1]],
                    [output[0],{'type':'image','text':'unexpected'}]):
            with self.assertRaises(AssertionError):mcp_output_text(bad)


    def test_current_gateway_cli_roundtrip_and_exact_tool_delivery(self):
        from http.server import ThreadingHTTPServer
        import threading
        from tests.codex_collect_checks import ScriptedResponses, NativeCodex
        server=ThreadingHTTPServer(('127.0.0.1',0),ScriptedResponses)
        server.captures,server.capture_lock=[],threading.Lock()
        server.mixed_tools=True
        server.auxiliary_tool="list_mcp_resources"
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config
        def local_config(home,*args):
            original(home,*args)
            path=home/'config.toml'
            text=path.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1')
            text=text.replace('requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0')
            path.write_text(text)
        try:
            with tempfile.TemporaryDirectory() as d, patch.object(codex_gateway,'write_config',local_config):
                root=Path(d);folder=root/'natural'/'actor';folder.mkdir(parents=True)
                events=queue.Queue();model='openai/gpt-6.1-sol'
                tools=[{'type':'function','name':'confirm_service','description':'Read service status.',
                        'parameters':{'type':'object','properties':{}}},
                       {'type':'function','name':'bash','description':'Execute a workstation command.',
                        'parameters':{'type':'object','properties':{'command':{'type':'string'}}}}]
                harness=codex_gateway.harness_registration('off',model)
                agent=run.codex_agent.CodexAgent('actor',events,folder=folder/'codex',
                    model=model,thinking_level='high',tools=tools,active_tools=['confirm_service','bash'],
                    goal_mode='off',api_base=codex_gateway.AXONHUB_BASE,api_key='offline-fixture',
                    registered_harness=harness)
                try:
                    ready=run.codex_agent.wait_ready(events,['actor'])['actor']
                    agent.prompt('Service fixture request.')
                    NativeCodex().drain(agent,events,folder)
                finally:agent.close()
                run.save(root/'registration.json',{'harness':harness})
                run.save(folder/'result.json',{'status':'collected','codex_session':ready})
                import export_atif
                result=export_atif.export_actor(root,'natural','actor')
                from phase1 import codex_native_review
                raw_files={str(p.relative_to(root)):run.sha(p) for p in root.rglob('*') if p.is_file()}
                run.save(root/'evidence-manifest.json',{'files':raw_files})
                native=codex_native_review.actor_evidence(root,'actor',sealed=True)
                self.assertTrue(all(x['sdk_delivery_verified'] for x in native['tool_delivery'].values()))
                for step in (1,2):
                    codex_native_review.response(root,{},'actor',step,sealed=True)
                event_path=next((folder/'trace').glob('*-tool-*.json'))
                call=run.load(event_path);event={'actor':'actor','result':call['result']}
                codex_native_review.delivered(root,{},event,{'call_id':call['call_id']},2,sealed=True)
                # A changed controller projection cannot be accepted as native text.
                changed=folder/'trace/0001.response.json';original=changed.read_bytes()
                value=run.load(changed);value['output'][0]['arguments']='{"changed":true}'
                run.save(changed,value)
                with self.assertRaises(ValueError):
                    codex_native_review.response(root,{},'actor',1,sealed=False)
                changed.write_bytes(original)
                self.assertTrue(result['native_continuity_passed'])
                self.assertEqual(result['tool_results'],1)
                raw=[json.loads(p.read_text()) for p in (folder/'codex/native').glob('*.json')]
                self.assertFalse(any(x.get('message',{}).get('params',{}).get('item',{}).get('type')=='additional_tools' for x in raw))
                self.assertEqual(len(server.captures),2)
                self.assertEqual(harness['workstation_context'],codex_gateway.WORKSTATION_CONTEXT)
                self.assertIn(codex_gateway.WORKSTATION_CONTEXT,json.dumps(server.captures[0]['input']))
                sent=[json.loads(p.read_text())['message'] for p in (folder/'codex/native').glob('*.json')]
                starts=[x['params'] for x in sent if x.get('method')=='thread/start']
                self.assertEqual(len(starts),1)
                self.assertEqual(starts[0]['sandbox'],'read-only')
                for request in server.captures:
                    self.assertFalse(any(x.get('type')=='additional_tools' for x in request['input']))
                    self.assertEqual({t['name'] for t in request['tools'] if t['type']=='function'},set(codex_gateway.NATIVE_TOOLS))
                    namespaces=[t for t in request['tools'] if t['type']=='namespace']
                    self.assertEqual([t['name'] for t in namespaces],['mcp__work'])
                    self.assertEqual({t['name'] for t in namespaces[0]['tools']},{'confirm_service','bash'})
                    self.assertTrue(all(t['type'] in ('function','namespace') for t in request['tools']))
        finally:server.shutdown();server.server_close()


    def test_all_selected_models_have_native_profiles(self):
        for model in ('openai/gpt-6.1-sol','openai/gpt-6.1-terra','openai/gpt-6-luna'):
            with self.subTest(model=model):
                catalog=codex_gateway.gateway_catalog(model,'high')
                self.assertEqual(catalog['model'],model)
                self.assertEqual(catalog['inference_calls'],0)

    def test_phase1_preparation_registers_native_gateway_without_changing_business(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();key=root/'key';key.write_text('offline-fixture');key.chmod(0o600)
            registration=root/'registrations'/'native'
            model='openai/gpt-6.1-sol'
            with patch.object(run,'REGISTRATIONS',registration.parent), patch.object(run,'MODELS',{'model':model}), patch.object(run,'UPSTREAM_MODELS',{'model':model}), patch.object(run,'verify_routes',return_value={}):
                run.prepare(root/'output',registration,key,run_controls=False,
                    scenario='engineering-capacity',study_mode='phase1',harness_kind='codex',goal_mode='off')
            prepared=run.load(registration/'registration.json')
            self.assertEqual(prepared['harness']['authentication'],'axonhub')
            self.assertEqual(prepared['harness']['kind'],'codex')
            self.assertEqual(prepared['api_base'],codex_gateway.AXONHUB_BASE)
            self.assertEqual(prepared['study_mode'],'phase1')
            from phase1 import carrier_registration, channel_design
            self.assertTrue(carrier_registration.valid(prepared))
            self.assertTrue(channel_design.valid_registered_exposure(prepared))
            self.assertEqual(prepared['harness']['goal_mode'],'off')
            self.assertEqual(prepared['models'],{'model':model})
