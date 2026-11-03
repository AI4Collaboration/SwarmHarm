"""Native gateway and record-binding checks; no hosted inference."""
import json
import queue
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import run
import codex_gateway
from phase2 import trace_release, trace_review
import record_surface


class NativeHarnessChecks(unittest.TestCase):
    def test_family_defaults_never_fall_back_to_pi(self):
        self.assertEqual(run.guardrails.native_harness({'model':'openai/gpt-5.6-sol'}),'codex')
        self.assertEqual(run.guardrails.native_harness({'model':'anthropic/claude-haiku-5.5'}),'claude-code')
        with self.assertRaises(ValueError):
            run.guardrails.native_harness({'model':'unsupported/model'})
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run.save(root/'registration.json',{'models':{'model':'unsupported/model'},'harness':{'kind':'pi-sdk'}})
            with patch.object(run,'REGISTRATIONS',root/'regs'), self.assertRaisesRegex(ValueError,'Pi is historical only'):
                run.collect(root,root/'regs'/'test')

    def test_real_codex_startup_preserves_session_path_before_first_turn(self):
        from codex_session import CodexAgent
        events=queue.Queue()
        with tempfile.TemporaryDirectory() as d:
            agent=CodexAgent('startup',events,folder=Path(d)/'codex',
                model='openai/gpt-5.6-sol',thinking_level='high',tools=[],active_tools=[],
                goal_mode='off',api_base=codex_gateway.AXONHUB_BASE,
                api_key='offline-startup-no-inference')
            try:
                event=events.get(timeout=60)[1]
                self.assertEqual(event['type'],'ready',event)
                surface=record_surface.NativeRecordSurface(Path(d),['startup'],harness='codex')
                surface.bind('startup',event['session_file'])
                self.assertEqual(surface.directory('startup'),Path(event['session_file']).parent)
            finally:
                agent.close()
            self.assertFalse(agent.inputs)

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

    def test_claude_and_codex_records_are_read_without_pi_conversion(self):
        rows=[{'type':'user','uuid':'cc-user','message':{'role':'user','content':'SR-1-01'}},
              {'type':'assistant','uuid':'cc-assistant','message':{'role':'assistant','content':[{'type':'text','text':'done'}]}},
              {'type':'response_item','timestamp':'2026-11-03T12:00:00Z','payload':{'type':'message','id':'msg-1','role':'user','content':[{'type':'input_text','text':'SR-1-02'}]}}]
        original={'session.jsonl':('\n'.join(map(json.dumps,rows))+'\n').encode()}
        live=trace_release.message_entries(original)
        reviewed,invalid=trace_review.entries(original)
        self.assertEqual(live,reviewed)
        self.assertEqual(len(live),3)
        self.assertEqual(invalid,[])
        changed={'session.jsonl':original['session.jsonl'].replace(b'SR-1-01',b'local-1')}
        self.assertNotEqual(trace_release.message_entries(changed)['cc-user'],live['cc-user'])
        self.assertEqual(trace_release.message_entries(original),live)
        duplicate={'session.jsonl':original['session.jsonl']+json.dumps(rows[0]).encode()+b'\n'}
        self.assertTrue(trace_review.entries(duplicate)[1])

    def test_native_surface_binds_own_record_then_uses_retained_copy_on_close(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();actual=root/'private-codex';actual.mkdir()
            (actual/'session.jsonl').write_text('{}\n')
            surface=record_surface.NativeRecordSurface(root,['a'],harness='codex')
            surface.bind('a',actual/'session.jsonl')
            self.assertEqual(surface.directory('a'),actual)
            self.assertEqual(surface.view,'/tmp/agent/activity')
            with self.assertRaises(ValueError):surface.bind('other',actual/'session.jsonl')
            surface.bound_directories.pop('a')
            self.assertEqual(surface.directory('a'),root/'a'/'codex')

    def test_native_trace_preparation_freezes_harness_and_gateway(self):
        for model,harness in [('anthropic/claude-haiku-5.5','claude-code'),('openai/gpt-5.6-sol','codex')]:
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as d:
                root=Path(d).resolve(); key=root/'host-key';key.write_text('offline-fixture');key.chmod(0o600)
                registration=root/'registrations'/'native'
                with patch.object(run,'REGISTRATIONS',registration.parent), patch.object(run,'MODELS',{'model':model}), patch.object(run,'UPSTREAM_MODELS',{'model':model}), patch.object(run,'verify_routes',return_value={}), patch.object(run.claude_agent,'gateway_catalog',return_value={'model':model}):
                    run.prepare(root/'output',registration,key,run_controls=False,
                        scenario='knowledge-work',study_mode='phase2-component',
                        component_family='trace-integrity',harness_kind=harness,goal_mode='off')
                prepared=json.loads((registration/'registration.json').read_text())
                self.assertEqual(prepared['harness']['kind'],harness)
                self.assertEqual(prepared['harness']['authentication'],'axonhub')
                self.assertEqual(prepared['api_base'],codex_gateway.AXONHUB_BASE)
                self.assertTrue(prepared['live_collection_permitted'])
                self.assertEqual(prepared['component_truth']['native_record_harness'],harness)
                self.assertNotIn('offline-fixture',(registration/'registration.json').read_text())
