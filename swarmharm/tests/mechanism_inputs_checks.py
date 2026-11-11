"""Executable mechanism paths, domain isolation and honest input exports."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs as inputs
from scripts.inspect_unified_input import build_preview, main


class MechanismInputChecks(unittest.TestCase):
    def test_declared_paths_and_corrected_bindings_in_every_domain(self):
        for domain in inputs.DOMAINS:
            for mechanism in inputs.implemented():
                with self.subTest(domain=domain, mechanism=mechanism):
                    manifest, subjects = build_preview(domain, inputs.MECHANISMS[mechanism]['preset'],
                                                       mechanism=mechanism)
                    result = inputs.validate_paths(mechanism, manifest['assignments'])
                    self.assertEqual(result['path_validation'], 'passed')
                    self.assertEqual(result['model_behavior'], 'not_tested')
                    self.assertEqual(len(subjects['tasks']), 4)
                    self.assertEqual(manifest['communication_start']['supplied_messages'], [])
                    for task in subjects['tasks'].values():
                        self.assertNotIn(mechanism, task)
                        self.assertNotIn(result['criterion'], task)

    def test_wrong_binding_cannot_claim_a_mechanism(self):
        manifest, _ = build_preview('knowledge-work', 'records', mechanism='evidence-tampering')
        plan = deepcopy(manifest['assignments'])
        for row in plan.values():
            row['world_config']['verification']['completion_evidence'] = 'executed'
        with self.assertRaises(ValueError):
            inputs.validate_plan('evidence-tampering', plan)

    def test_unimplemented_mechanism_never_exports_a_fallback(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)/'inputs'
            with self.assertRaises(SystemExit):
                main(['--mechanism', 'all', '--scenario', 'all', '--output', str(output)])
            self.assertFalse(output.exists())

    def test_export_keeps_coverage_and_model_validation_separate(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)/'inputs'
            main(['--mechanism', 'implemented', '--scenario', 'all', '--output', str(output)])
            index = json.loads((output/'manifest.json').read_text())
            self.assertEqual(index['planned_count'], 32)
            self.assertEqual(index['exported_count'], len(inputs.implemented())*4)
            self.assertEqual(index['model_behavior'], 'not_tested')
            for entry in index['inputs'].values():
                manifest = json.loads((output/entry['manifest']).read_text())
                self.assertEqual(manifest['validation']['execution_paths'], 'not_run')
                self.assertEqual(manifest['mechanism_contract']['visibility'], 'operator_only')


if __name__ == '__main__':
    unittest.main()
