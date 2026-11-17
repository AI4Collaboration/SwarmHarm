"""Batch input seals remain distinct from the reviewed scientific case ledger."""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
CHECK = runpy.run_path(str(ROOT/'scripts/check_dataset_admission_contract.py'))
batch_registrations = CHECK['batch_registrations']


class DatasetAdmissionChecks(unittest.TestCase):
    def test_generated_batch_inputs_require_their_original_seal_and_path_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registrations = root/'swarmharm/registrations'
            folder = registrations/'batch-fixture'
            folder.mkdir(parents=True)
            registration, seal = folder/'registration.json', folder/'registration-seal.json'
            registration.write_text(json.dumps({'study_mode':'unified',
                'source_retention':{'mode':'local'},
                'mechanism_contract':{'path_validation':'passed'}}))
            seal.write_text(json.dumps({'sha256':hashlib.sha256(registration.read_bytes()).hexdigest()}))
            with patch.dict(batch_registrations.__globals__, ROOT=root, REGISTRATIONS=registrations):
                self.assertEqual(batch_registrations(), {str(folder.relative_to(root))})
                registration.write_bytes(registration.read_bytes()+b'\n')
                with self.assertRaisesRegex(SystemExit, 'seal differs'):
                    batch_registrations()
                value = json.loads(registration.read_text())
                value['mechanism_contract']['path_validation'] = 'failed'
                registration.write_text(json.dumps(value))
                seal.write_text(json.dumps({'sha256':hashlib.sha256(registration.read_bytes()).hexdigest()}))
                with self.assertRaisesRegex(SystemExit, 'lacks validated native inputs'):
                    batch_registrations()
                seal.unlink()
                with self.assertRaisesRegex(SystemExit, 'lacks sealed inputs'):
                    batch_registrations()


if __name__ == '__main__':
    unittest.main()
