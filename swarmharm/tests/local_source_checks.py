"""Local-only collection retains source/registration seals without a remote."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import run


class LocalSourceChecks(unittest.TestCase):
    def test_root_review_entry_loads_native_exporter(self):
        result = subprocess.run([sys.executable, '-c',
            "import sys; sys.path.insert(0, 'swarmharm'); import review; "
            "import export_atif; print(export_atif.__file__)"],
            cwd=run.REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).resolve(), run.REPO/'shared/export_atif.py')

    def test_root_entry_loads_the_reporting_test_package(self):
        result = subprocess.run([sys.executable, '-c',
            "import sys; sys.path.insert(0, 'swarmharm'); import run; "
            "import tests.unified_runtime_checks as module; print(module.__file__)"],
            cwd=run.REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).resolve(),
                         run.HERE/'tests/unified_runtime_checks.py')

    def fixture(self, base):
        repo, raw = base/'repo', base/'raw'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        self.git = lambda *args: subprocess.check_output(
            ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
             *args], cwd=repo, text=True).strip()
        (repo/'source.py').write_text('value = 1\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'source')
        source = self.git('rev-parse', 'HEAD')
        registration = repo/'registration'
        registration.mkdir()
        (raw/'code').mkdir(parents=True)
        shutil.copy2(repo/'source.py', raw/'code/source.py')
        reg = {'source_retention': {'mode': 'local', 'commit': source},
               'code_hashes': {'source.py': run.sha(repo/'source.py')},
               'input_hashes': {}, 'task_hashes': {}}
        for name in run.FROZEN_REGISTRATION_FILES:
            run.save(raw/name, reg if name == 'registration.json' else {})
            shutil.copy2(raw/name, registration/name)
        self.git('add', '.')
        self.git('commit', '-qm', 'registration')
        return repo, raw, registration, reg

    def test_local_collection_keeps_committed_seals_without_contacting_origin(self):
        with TemporaryDirectory() as directory:
            repo, raw, registration, reg = self.fixture(Path(directory))
            original = subprocess.check_output
            with patch.object(run, 'REPO', repo), patch.object(
                    run.subprocess, 'check_output', wraps=original) as commands:
                run.verify_collection_freeze(raw, registration, reg)
            self.assertFalse(any('ls-remote' in call.args[0] for call in commands.call_args_list))

    def test_local_collection_rejects_dirty_and_changed_frozen_source(self):
        with TemporaryDirectory() as directory:
            repo, raw, registration, reg = self.fixture(Path(directory))
            with patch.object(run, 'REPO', repo):
                (repo/'source.py').write_text('value = 2\n')
                with self.assertRaisesRegex(RuntimeError, 'clean'):
                    run.verify_collection_freeze(raw, registration, reg)
                self.git('checkout', '--', 'source.py')
                (raw/'code/source.py').write_text('value = 2\n')
                with self.assertRaisesRegex(RuntimeError, 'Frozen source hash differs'):
                    run.verify_collection_freeze(raw, registration, reg)

    def test_local_collection_rejects_unretained_history_and_unknown_policy(self):
        with TemporaryDirectory() as directory:
            repo, raw, registration, reg = self.fixture(Path(directory))
            with patch.object(run, 'REPO', repo):
                reg['source_retention']['commit'] = '0'*40
                with self.assertRaisesRegex(RuntimeError, 'not retained'):
                    run.verify_collection_freeze(raw, registration, reg)
                reg['source_retention']['mode'] = 'unchecked'
                with self.assertRaisesRegex(RuntimeError, 'Unknown source retention'):
                    run.verify_collection_freeze(raw, registration, reg)

    def test_old_registration_still_requires_origin(self):
        with TemporaryDirectory() as directory:
            repo, raw, registration, reg = self.fixture(Path(directory))
            reg.pop('source_retention')
            original = subprocess.check_output
            def output(argv, **kwargs):
                if 'ls-remote' in argv:
                    return '0'*40 + '\trefs/heads/main\n'
                return original(argv, **kwargs)
            with patch.object(run, 'REPO', repo), patch.object(
                    run.subprocess, 'check_output', side_effect=output):
                with self.assertRaisesRegex(RuntimeError, 'pushed to origin'):
                    run.verify_collection_freeze(raw, registration, reg)


class CompatibleApiChecks(unittest.TestCase):
    def test_custom_model_catalog_is_independent_of_openrouter(self):
        with patch.object(run, 'catalog', return_value={'model_found': True}) as catalog:
            route = run.verify_routes(None, api_base='https://example.test/api/v1/')
        catalog.assert_called_once_with('https://example.test/api/v1/models',
                                        next(iter(run.MODELS.values())), None)
        self.assertEqual(route['responses_endpoint'], 'https://example.test/api/v1/responses')
        self.assertFalse(route['inference_entitlement_verified'])
        self.assertNotIn('openrouter', route)

    def test_optional_catalog_and_invalid_urls(self):
        from urllib.error import HTTPError
        with patch.object(run, 'catalog', side_effect=HTTPError('url', 404, '', {}, None)):
            route = run.verify_routes(None, api_base='http://127.0.0.1:1234/v1')
        self.assertIsNone(route['catalog']['model_found'])
        with patch.object(run, 'catalog', return_value={'model_found': False}):
            with self.assertRaisesRegex(ValueError, 'absent'):
                run.verify_routes(None, api_base='https://example.test/v1')
        for value in ('file:///tmp/key', 'https://user:key@example.test/v1',
                      'https://example.test/v1?key=secret', 'https://example.test/v1/responses'):
            with self.assertRaises(ValueError):
                run.guardrails.api_base_url(value)

    def test_native_model_identity_and_secret_stay_separate(self):
        import tomllib
        gateway = run.codex_gateway
        with gateway.isolated_home() as home:
            native = gateway.native_catalog(home)
            model = next(row['slug'] for row in native['models'] if row['slug'].startswith('gpt-'))
            for model_id in (model, 'openai/'+model):
                gateway.write_config(home, home, home/'tools.json', home/'call.sock',
                                     model_id, 'high', native, api_base='https://example.test/v1')
                config = tomllib.loads((home/'config.toml').read_text())
                self.assertEqual(config['model'], model_id)
                provider = config['model_providers'][config['model_provider']]
                self.assertEqual(provider['base_url'], 'https://example.test/v1')
                self.assertEqual(provider['wire_api'], 'responses')
                self.assertFalse(provider['supports_websockets'])
            environment = gateway.gateway_env(home, 'https://example.test/v1', 'fixture-secret')
            self.assertEqual(environment['SWARMHARM_AXONHUB_KEY'], 'fixture-secret')
            self.assertNotIn('fixture-secret', (home/'config.toml').read_text())
            self.assertNotIn('OPENAI_API_KEY', environment)
            self.assertNotIn('auth.json', {path.name for path in home.iterdir()})
