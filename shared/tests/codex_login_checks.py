"""Codex login routing and isolation checks; no hosted inference."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

import codex_agent
import codex_gateway
import model_lineup
import model_session

ROOT = Path(__file__).resolve().parents[2]


class CodexLoginChecks(unittest.TestCase):
    def test_npm_launcher_resolves_nested_hoisted_and_bundled_native_packages(self):
        for layout in ('nested', 'hoisted', 'bundled'):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as directory:
                package = Path(directory)/'node_modules/@openai/codex'
                launcher = package/'bin/codex.js'
                launcher.parent.mkdir(parents=True)
                launcher.write_text('// npm launcher')
                vendor = {'nested': package/'node_modules/@openai/codex-linux-x64/vendor',
                          'hoisted': package.parent/'codex-linux-x64/vendor',
                          'bundled': package/'vendor'}[layout]
                binary = vendor/'x86_64-unknown-linux-musl/bin/codex'
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b'native executable fixture')
                with patch.dict(os.environ, {'SWARMHARM_NATIVE_CODEX': str(launcher)}), \
                        patch.object(codex_gateway.platform, 'machine', return_value='x86_64'), \
                        patch.object(codex_gateway.platform, 'system', return_value='Linux'):
                    self.assertEqual(codex_gateway.codex_binary(), str(binary.resolve()))
                    binary.unlink()
                    with self.assertRaisesRegex(RuntimeError, 'Native Codex package is missing'):
                        codex_gateway.codex_binary()

    def test_local_login_bypasses_the_api_bridge_and_provider_mapping(self):
        with patch.object(model_session, 'ChatBridge', side_effect=AssertionError('API bridge used')), \
                patch.object(codex_agent, 'CodexAgent') as agent:
            model_session.create('codex', 'one', object(), codex_auth='chatgpt',
                model='openai/gpt-6.1-terra', served_model='obsolete-api-model',
                api_base='https://example.test/v1', api_key='host-only-fixture')
            options = agent.call_args.kwargs
            self.assertEqual(options['model'], 'gpt-6.1-terra')
            self.assertEqual(options['registered_model'], 'openai/gpt-6.1-terra')
            self.assertIsNone(options['api_base'])
            self.assertIsNone(options['api_key'])

    def test_subscription_config_and_environment_cannot_select_api_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            catalog = {'models':[{'slug':'gpt-6.1-terra', 'base_instructions':'Native instructions'}]}
            codex_agent.write_config(home, home, home/'tools.json', home/'call.sock',
                'gpt-6.1-terra', 'high', catalog)
            config = tomllib.loads((home/'config.toml').read_text())
            self.assertEqual(config['model_provider'], 'openai')
            self.assertEqual(config['forced_login_method'], 'chatgpt')
            self.assertNotIn('model_providers', config)
            self.assertEqual(config['mcp_servers']['work']['default_tools_approval_mode'], 'approve')
            profile = json.loads((home/'catalog.json').read_text())['models'][0]
            self.assertEqual(profile['base_instructions'], 'Native instructions')
            self.assertIsNone(profile['tool_mode'])
            with patch.dict(os.environ, {'OPENAI_API_KEY':'api-fixture', 'NVIDIA_API_KEY':'nvidia-fixture',
                    'OPENAI_BASE_URL':'https://example.test/v1', 'CODEX_AUTH_JSON':'auth-fixture'}):
                env = codex_agent.subscription_env(home)
            self.assertEqual(env['CODEX_HOME'], str(home))
            for name in ('OPENAI_API_KEY', 'NVIDIA_API_KEY', 'OPENAI_BASE_URL', 'CODEX_AUTH_JSON'):
                self.assertNotIn(name, env)

    def test_mixed_lineup_uses_native_terra_and_seven_api_models(self):
        rows = model_lineup.selection()
        local = [row for row in rows if row['codex_auth'] == 'chatgpt']
        self.assertEqual(len(local), 4)
        self.assertEqual(len(rows)-len(local), 7)
        self.assertTrue(all(row['harness']=='codex' and row['served_model']==row['model'].removeprefix('openai/') for row in local))
        self.assertEqual(next(row for row in local if row['name']=='terra')['model'], 'openai/gpt-6.1-terra')

    def test_both_study_previews_ignore_api_credentials_for_codex(self):
        for script in ('rollouts/run_matrix.py', 'swarmharm/run_matrix.py'):
            with self.subTest(script=script):
                env = dict(os.environ, OPENAI_BASE_URL='unused-invalid-provider-url',
                    OPENAI_API_KEY_FILE='/missing/api-key')
                output = subprocess.check_output([sys.executable, str(ROOT/script),
                    '--model','openai/gpt-6.1-terra','--populations','4'], env=env, cwd=ROOT, text=True)
                rows = [json.loads(line) for line in output.splitlines()]
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual(row['codex_auth'], 'chatgpt')
                    self.assertEqual(row['api_protocol'], 'native')
                    self.assertEqual(row['served_model'], 'gpt-6.1-terra')
                    self.assertIsNone(row['base_url'] if script.startswith('rollouts/') else row['api_base'])


if __name__ == '__main__':
    unittest.main()
