"""Source sealing and independent final-package checks without hosted inference."""

import base64
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from swarmform.inputs import build, verify_packages

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('swarmform_entry', ROOT / 'scripts/run_swarmform.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class RegistrationChecks(unittest.TestCase):
    def test_harbor_packages_retain_exact_prompts_and_current_three_agent_adapter(self):
        inputs, _, _ = build('november')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            files = entry.write_tasks(root, inputs, entry.IMAGE)
            self.assertEqual(len(files), 6)
            for actor, prompts in inputs['prompts'].items():
                self.assertEqual((root / 'tasks' / actor / 'instruction.md').read_text(), '\n\n'.join(prompts))
            self.assertTrue(all(entry.sha(root / path) == digest for path, digest in files.items()))

    def test_frozen_check_rejects_changed_input_before_native_validation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); registration = root / 'registration'; registration.mkdir()
            output = root / 'raw'; output.mkdir()
            entry.save(output / 'input.json', {'version': 1})
            value = {'source_commit': 'source', 'code_hashes': {},
                     'input_hashes': {'input.json': entry.sha(output / 'input.json')}, 'task_hashes': {}}
            for folder in (registration, output):
                entry.save(folder / 'registration.json', value)
                entry.save(folder / 'registration-seal.json', {'sha256': entry.sha(folder / 'registration.json')})
            entry.save(output / 'input.json', {'version': 2})
            with patch.object(entry, 'ROOT', root), patch.object(entry, 'published_head', return_value='current'), \
                    patch.object(entry, 'git', return_value='tracked'), \
                    patch.object(entry, 'check_runtime', side_effect=AssertionError('Too late')):
                with self.assertRaisesRegex(RuntimeError, 'Prepared input differs'):
                    entry.verify_frozen(registration, output)

    def test_package_check_does_not_treat_stale_or_different_owner_copy_as_delivery(self):
        def snapshot(office, packed_ledger, private_ledger):
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as z:
                z.writestr('ledger.csv', packed_ledger)
                z.writestr('manifest.json', json.dumps({'office': office, 'batch': 'opening',
                    'ledger_sha256': entry.sha256(packed_ledger).hexdigest()}))
            return {'/var/tmp/exports': {'/var/tmp/exports/Northline-opening.zip': base64.b64encode(data.getvalue()).decode()},
                    '/workspace': {'/workspace/releases/opening/ledger.csv': base64.b64encode(private_ledger).decode()}}
        self.assertTrue(verify_packages('Northline', snapshot('Northline', b'new', b'new'))['opening']['matches_authored_ledger'])
        self.assertFalse(verify_packages('Northline', snapshot('Northline', b'old', b'new'))['opening']['matches_authored_ledger'])
        self.assertFalse(verify_packages('Northline', snapshot('Aster', b'new', b'new'))['opening']['matches_authored_ledger'])
        self.assertFalse(verify_packages('Northline', {})['opening']['matches_authored_ledger'])


if __name__ == '__main__':
    unittest.main()
