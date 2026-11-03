"""Gateway isolation and actual Claude SDK delivery, with a local HTTP fixture."""
from contextlib import redirect_stdout
from copy import deepcopy
import io, json, os, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import run
from phase1 import carrier_registration, claude_native_review

c = run.claude_agent
MODEL = 'anthropic/claude-opus-5.5'


class GatewayChecks(unittest.TestCase):
    def test_gateway_drops_personal_auth_and_pins_internal_models(self):
        with patch.dict(os.environ, {'PATH':'/bin','HOME':'/tmp','CLAUDE_CODE_OAUTH_TOKEN':'personal',
                'ANTHROPIC_API_KEY':'direct','ANTHROPIC_BASE_URL':'https://wrong.invalid',
                'CLAUDE_CONFIG_DIR':'/personal','ANTHROPIC_DEFAULT_SONNET_MODEL':'other'}, clear=True):
            env=c.gateway_env(c.AXONHUB_BASE,'fixture-token',MODEL,'/private-config')
        self.assertNotIn('CLAUDE_CODE_OAUTH_TOKEN',env)
        self.assertNotIn('ANTHROPIC_API_KEY',env)
        self.assertEqual(env['ANTHROPIC_BASE_URL'],'https://lmportal.iefbr14.xyz')
        self.assertEqual(env['CLAUDE_CONFIG_DIR'],'/private-config')
        self.assertEqual(env['ANTHROPIC_DEFAULT_SONNET_MODEL'],MODEL)
        self.assertEqual(env['ANTHROPIC_DEFAULT_HAIKU_MODEL'],MODEL)
        for wrong in ('https://api.anthropic.com/v1','https://wrong.invalid/v1'):
            with self.assertRaises(ValueError):c.gateway_env(wrong,'secret',MODEL,'/tmp')
        for wrong in ('haiku','anthropic/claude-haiku-latest','anthropic/claude-haiku-5.5:batch'):
            with self.assertRaises(ValueError):c.gateway_model_ids(wrong)

    def test_gateway_carrier_preparation_seals_route_and_rejects_subscription_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);key=root/'key';key.write_text('fixture');key.chmod(0o600)
            with patch.object(run,'REGISTRATIONS',root/'registrations'), patch.object(run,'MODELS',{'claude':MODEL}), \
                 patch.object(run,'UPSTREAM_MODELS',{'claude':MODEL}), patch.object(run,'verify_routes',return_value={}), \
                 patch.object(c,'gateway_catalog',return_value={'model_and_effort_found':True}), \
                 patch.object(c,'subscription_auth',side_effect=AssertionError('No personal login')), \
                 redirect_stdout(io.StringIO()):
                run.prepare(root/'output',root/'registrations'/'case',key,run_controls=False,
                    harness_kind='claude-code',study_mode='phase1',phase1_carrier='data_object')
            reg=run.load(root/'output/registration.json')
            self.assertTrue(carrier_registration.valid(reg))
            self.assertEqual(reg['endpoint'],c.AXONHUB_BASE+'/messages')
            self.assertNotIn('fixture',json.dumps(reg['harness']))
            bad=deepcopy(reg);bad['harness']['authentication']='claude-subscription'
            self.assertFalse(carrier_registration.valid(bad))

    def test_cli_rejects_non_gateway_base_before_preparation(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'output'
            result=subprocess.run([sys.executable,'-B',str(run.HERE/'run.py'),
                '--phase','prepare','--harness','claude-code','--model-id',MODEL,
                '--key-file',str(Path(temp)/'key'),'--api-base','https://api.anthropic.com/v1',
                '--output',str(output),'--registration-dir',str(run.REGISTRATIONS/'never-created')],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('Claude gateway requires the AxonHub API base',result.stderr)
            self.assertFalse(output.exists())

    def test_real_gateway_sdk_tool_roundtrip_and_native_forgery_rejection(self):
        fixture=run.module('gateway_local_fixture',Path(__file__).with_name('claude_collect_checks.py'))
        class Handler(fixture.ScriptedMessages):
            requests=[]
            authorization=[]
            def do_POST(self):
                type(self).authorization.append(self.headers.get('Authorization'))
                super().do_POST()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'natural'/'actor';(folder/'trace').mkdir(parents=True)
            tool={'name':'confirm_service','description':'Read service status.',
                'parameters':{'type':'object','properties':{},'additionalProperties':False}}
            events=c.new_queue()
            with patch.object(c,'AXONHUB_BASE',f'http://127.0.0.1:{server.server_port}/v1'):
                agent=c.ClaudeAgent('actor',events,folder=folder/'claude',model=MODEL,
                    thinking_level='high',max_output_tokens=1024,request_timeout_ms=10000,
                    tools=[tool],active_tools=['confirm_service'],goal_mode='off',
                    api_base=c.AXONHUB_BASE,api_key='local-fixture-token')
            try:
                c.wait_ready(events,['actor']);agent.prompt('Check service availability.')
                call_id=None
                while True:
                    _,message=events.get(timeout=40)
                    if message['type']=='request':
                        run.save(folder/'trace'/f"{message['turn']:04d}.request.json",message['payload'])
                    elif message['type']=='provider_response':
                        run.save(folder/'trace'/f"{message['turn']:04d}.response.json",message['event']['response'])
                    elif message['type']=='tool_call':
                        call_id=message['call_id'];agent.reply(message['id'],output='{"status":"available"}')
                    elif message['type']=='settled':
                        self.assertFalse(message.get('error_message'),message);break
                    elif message['type'] in ('fatal','exited'):self.fail(str(message))
                self.assertIsNotNone(call_id)
            finally:agent.close()
            self.assertTrue(Handler.requests)
            self.assertTrue(all(r['model']==MODEL for r in Handler.requests))
            self.assertTrue(all(a=='Bearer local-fixture-token' for a in Handler.authorization))
            self.assertTrue(all(r.get('output_config',{}).get('effort')=='high'
                                for r in Handler.requests if r.get('tools')))
            reg={'harness':{'accepted_native_model_ids':c.gateway_model_ids(MODEL)},
                 'models':{'claude':MODEL},'plan':{'natural':{'actor':{'provider':'claude'}}}}
            bound=claude_native_review.response(root,reg,'actor',1,sealed=False)
            event={'actor':'actor','step':1,'result':{'status':'available'}}
            found=claude_native_review.delivered(root,reg,event,{'call_id':call_id},2,sealed=False)
            self.assertTrue(bound['records']);self.assertTrue(found)
            run.save(root/'registration.json',reg)
            independent = subprocess.run([sys.executable,'-B','-c',
                'import json,sys; from pathlib import Path; from phase1 import claude_native_review as n; '
                'r=Path(sys.argv[1]); n.response(r,json.loads((r/"registration.json").read_text()),"actor",1,sealed=False)',
                str(root)],cwd=run.HERE,capture_output=True,text=True,
                env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'})
            self.assertEqual(independent.returncode,0,independent.stderr)
            path=folder/'trace/0001.response.json';original=path.read_bytes()
            value=run.load(path);value['output'][0]['arguments']='{"forged":true}';run.save(path,value)
            with self.assertRaisesRegex(ValueError,'native SDK calls'):
                claude_native_review.response(root,reg,'actor',1,sealed=False)
            path.write_bytes(original)
            with self.assertRaisesRegex(ValueError,'not delivered'):
                claude_native_review.delivered(root,reg,event,{'call_id':'invented'},2,sealed=False)
            self.assertNotIn('local-fixture-token',''.join(p.read_text() for p in (folder/'claude/native').glob('*.json')))


if __name__=='__main__':unittest.main()
