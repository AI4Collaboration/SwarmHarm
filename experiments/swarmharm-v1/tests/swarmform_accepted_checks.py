"""Accepted inputs execute their sealed source; no Docker or native calls."""
import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import swarmform_accepted_run as accepted
spec = importlib.util.spec_from_file_location('accepted_test_entry', ROOT / 'scripts/run_swarmform.py')
entry = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = entry
spec.loader.exec_module(entry)

FROZEN_RUNNER = '''from pathlib import Path
from types import SimpleNamespace
from sealed_identity import VALUE
ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'frozen-image'
def check_runtime(): return {'source': VALUE}
def verify(harness):
    if harness != {'pin': 'original'}: raise ValueError('harness pin')
codex_gateway = SimpleNamespace(verify_runtime=verify, gateway_catalog=lambda model, effort: {'model': model, 'effort': effort})
def credential_file(path, root): return Path(path)
class Collection:
    def __init__(self, output, reg, inputs, *, api_key): self.output = output
    def run(self): return {'collection_source': VALUE}
def finalize_collection(output, reg, inputs, report):
    return {**report, 'finalizer_source': VALUE, 'identifier': reg['identifier'], 'failures': []}
'''


class AcceptedChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name); self.root = self.base / 'main'
        self.package = self.base / 'bundle/worker_endpoint/event_pattern/knowledge-work'
        self.source = self.base / ('bundle/sources/' + 'a' * 40)
        self.output = self.base / 'raw'
        self.cell = 'worker_endpoint/event_pattern/Knowledge Work'
        self.manifest = {'worker_visible_sha256': 'unchanged', 'effective_settings': {'old': True}}
        for name in accepted.CONTROLLER_FILES:
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('current controller ' + name)
        for name, content in {'scripts/run_swarmform.py': FROZEN_RUNNER, 'scripts/sealed_identity.py': "VALUE = 'frozen-only'\n"}.items():
            p = self.source / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
        for name, value in {'input.json': {'original': True}, 'protected-truth.json': {'truth': True},
                            'input-manifest.json': self.manifest}.items(): entry.save(self.package / name, value)
        task = self.package / 'tasks/Juniper/instruction.md'; task.parent.mkdir(parents=True); task.write_text('original business task')
        self.original = {'identifier': 'accepted-old', 'source_commit': 'a' * 40, 'created_at': 'old',
            'matrix_cell': self.cell, 'domain': 'Knowledge Work', 'model': 'openai/gpt-6.1-sol',
            'models': {'openai': 'openai/gpt-6.1-sol'}, 'reasoning': 'high', 'image': 'frozen-image',
            'harness': {'pin': 'original'}, 'native_catalog': {'model': 'openai/gpt-6.1-sol', 'effort': 'high'},
            'runtime': {'source': 'frozen-only'}, 'input_sha256': entry.digest(self.manifest),
            'code_hashes': {n: accepted.sha(self.source / n) for n in ('scripts/run_swarmform.py', 'scripts/sealed_identity.py')},
            'input_hashes': {n: accepted.sha(self.package / n) for n in ('input.json', 'protected-truth.json')},
            'task_hashes': {'tasks/Juniper/instruction.md': accepted.sha(task)},
            'budget': {'original_budget': 1}, 'criteria': {'original_criterion': True}}
        entry.save(self.package / 'registration.json', self.original)
        seal = {'sha256': accepted.sha(self.package / 'registration.json')}
        entry.save(self.package / 'registration-seal.json', seal)
        old = self.root / 'experiments/swarmharm-v1/registrations/accepted-old'
        entry.save(old / 'registration.json', self.original); entry.save(old / 'registration-seal.json', seal)
        entry.save(self.base / 'bundle/index.json', {'cells': [{'cell': self.cell, 'directory': 'worker_endpoint/event_pattern/knowledge-work',
            'source': 'sources/' + 'a' * 40, 'registration_sha256': seal['sha256'], 'input_sha256': self.original['input_sha256'], 'acceptance': 'sustained_communication', 'rollout': 'accepted-old', 'trajectory_url': 'https://example.test/archive', 'trajectory_sha256': 'c' * 64}]})
        entry.save(self.root / 'docs/admission.json', {'status': 'admitted', 'matrix_cell': self.cell, 'input_sha256': self.original['input_sha256']})
        entry.save(self.root / 'docs/live-rollout-status.json', {'matrix': {'cells': {self.cell: {'status': 'admitted', 'evidence': 'docs/admission.json', 'current_model_result': {'identifier': 'accepted-old', 'status': 'reviewed', 'input_sha256': self.original['input_sha256'], 'trajectory_url': 'https://example.test/archive', 'archive_sha256': 'c' * 64, 'communication_review': {'three_agent_swarm': True, 'sustained_substantive_exchange': True}}}}}, 'maintained_registrations': []})
        self.args = argparse.Namespace(identifier='fresh-accepted', accepted_package=self.package, output=self.output,
            model='openai/gpt-6.1-sol', dataset_key='november', domain='Knowledge Work', deployment='worker_endpoint', encoding='event_pattern')
        for mock in (patch.object(entry, 'ROOT', self.root), patch.object(entry, 'published_head', return_value='b' * 40),
                     patch.object(entry, 'build', side_effect=AssertionError('Must not call current generator')),
                     patch.object(entry, 'check_runtime', side_effect=AssertionError('Must not check current runtime'))):
            mock.start(); self.addCleanup(mock.stop)

    def prepare(self):
        return entry.prepare(self.args)

    def verify(self, reg=None):
        reg = reg or accepted.read(self.output / 'registration.json')
        return accepted.verify_prepared(entry, reg, self.output, 'published-main', accepted.sha(self.output / 'registration.json'))

    def test_fresh_registration_preserves_old_input_runtime_and_result(self):
        result = self.prepare(); reg = accepted.read(self.output / 'registration.json')
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(self.verify(), reg)
        for key in self.original.keys() - {'identifier', 'created_at'}:
            self.assertEqual(reg[key], self.original[key])
        self.assertEqual(set(reg['accepted_package']['controller_code_hashes']), set(accepted.CONTROLLER_FILES))
        ledger = accepted.read(self.root / 'docs/live-rollout-status.json')
        self.assertEqual(ledger['matrix']['cells'][self.cell]['current_model_result']['identifier'], 'accepted-old')
        self.assertIn('experiments/swarmharm-v1/registrations/fresh-accepted', ledger['maintained_registrations'])

    def test_rejects_package_bytes_source_and_admission_drift(self):
        for path in (self.package / 'input.json', self.source / 'scripts/sealed_identity.py', self.root / 'docs/admission.json'):
            with self.subTest(path=path):
                before = path.read_bytes()
                path.write_text('{}')
                with self.assertRaises(ValueError): accepted.package_input(entry, self.package)
                path.write_bytes(before)

    def test_rejects_source_launcher_and_setting_changes_after_prepare(self):
        self.prepare()
        for path in (self.output / 'code/scripts/sealed_identity.py', self.root / 'scripts/swarmform_accepted_run.py', self.output / 'input.json'):
            with self.subTest(path=path):
                before = path.read_bytes(); path.write_text('changed')
                with self.assertRaises(ValueError): self.verify()
                path.write_bytes(before)
        reg = accepted.read(self.output / 'registration.json'); reg['harness'] = {'pin': 'changed'}
        with self.assertRaisesRegex(ValueError, 'runtime pins'): self.verify(reg)
        (self.output / 'code/unsealed.py').write_text('unexpected source')
        with self.assertRaisesRegex(ValueError, 'unsealed'): self.verify()

    def test_rejects_wrong_model_duplicate_identifier_and_started_output(self):
        self.args.model = 'openai/gpt-5.6-sol'
        with self.assertRaises(ValueError): self.prepare()
        self.args.model = 'openai/gpt-6.1-sol'; self.args.identifier = 'accepted-old'
        with self.assertRaises(FileExistsError): self.prepare()
        self.args.identifier = 'fresh-accepted'; self.prepare()
        with self.assertRaises(FileExistsError): self.prepare()
        (self.output / 'started.json').write_text('{}')
        # The existing collector opens its lock before the started check.
        real_open = Path.open; handles = []
        def tracked_open(path, *args, **kwargs):
            handle = real_open(path, *args, **kwargs)
            if path.name == '.collector.lock': handles.append(handle)
            return handle
        try:
            with patch.object(Path, 'open', tracked_open):
                with self.assertRaisesRegex(FileExistsError, 'already started'): entry.collect(self.args)
        finally:
            for handle in handles: handle.close()

    def test_rejects_registered_but_unaccepted_original_and_later_result_change(self):
        self.prepare()
        ledger_path = self.root / 'docs/live-rollout-status.json'
        ledger = accepted.read(ledger_path)
        # Same sealed original, exact input and forged positive index label;
        # only the actual accepted outcome changes to a preflight failure.
        ledger['matrix']['cells'][self.cell]['current_model_result']['status'] = 'launch_preflight_failed'
        entry.save(ledger_path, ledger)
        with self.assertRaisesRegex(ValueError, 'qualifying accepted'):
            accepted.package_input(entry, self.package)
        with self.assertRaisesRegex(ValueError, 'qualifying accepted'):
            self.verify()
        ledger['matrix']['cells'][self.cell]['current_model_result']['status'] = 'reviewed'
        ledger['matrix']['cells'][self.cell]['current_model_result']['archive_sha256'] = 'd' * 64
        entry.save(ledger_path, ledger)
        with self.assertRaisesRegex(ValueError, 'accepted trajectory'):
            accepted.package_input(entry, self.package)
        with self.assertRaisesRegex(ValueError, 'changed after preparation'):
            self.verify()

    def test_child_imports_only_frozen_collection_and_finalizer(self):
        self.prepare(); self.verify(); poison = self.base / 'poison'; poison.mkdir(); (poison / 'sealed_identity.py').write_text("raise AssertionError('current module imported')")
        key = self.base / 'key'; key.write_text('offline-only')
        with patch.dict(os.environ, {'PYTHONPATH': str(poison)}):
            result = accepted.dispatch('collect', self.output / 'code', self.output / 'registration.json', output=self.output, key_file=key)
        self.assertEqual(result['collection_source'], 'frozen-only')
        self.assertEqual(result['finalizer_source'], 'frozen-only')
        self.assertEqual(result['identifier'], 'fresh-accepted')

    def test_child_rejects_image_harness_and_native_catalog_drift(self):
        self.prepare(); reg = accepted.read(self.output / 'registration.json')
        for key, value in (('image', 'new-image'), ('harness', {'pin': 'wrong'}), ('native_catalog', {})):
            bad = deepcopy(reg); bad[key] = value; path = self.base / 'bad.json'; entry.save(path, bad)
            call = subprocess.run([sys.executable, '-I', '-B', str(Path(accepted.__file__)), 'inspect', str(self.output / 'code'), str(path)], capture_output=True, text=True)
            self.assertNotEqual(call.returncode, 0, key)

    def test_normal_prepare_keeps_current_path(self):
        del self.args.accepted_package
        with patch.object(entry, 'check_runtime', return_value={'current': True}), patch.object(entry, 'prepare_one', return_value={'normal': True}) as normal:
            self.assertEqual(entry.prepare(self.args), {'normal': True})
            normal.assert_called_once_with(self.args, 'b' * 40, {'current': True})


if __name__ == '__main__': unittest.main()
