"""Reviewable business-input export without starting an evaluation."""
import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import unified_delivery as scenario, world_config

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/inspect_unified_input.py'
SPEC = importlib.util.spec_from_file_location('inspect_unified_input', SCRIPT)
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)


class UnifiedInputPreviewChecks(unittest.TestCase):
    def test_export_entrypoint_is_in_sealed_source_dependencies(self):
        import run
        sealed = set(run.code_paths())
        self.assertIn(SCRIPT, sealed)
        for folder in (run.HERE/'configs', run.HERE/'tests/worlds'):
            examples = set(folder.glob('*.json'))
            self.assertTrue(examples)
            self.assertFalse(examples - sealed)

    def test_every_maintained_config_exports_with_matching_subject_inputs(self):
        folder = Path(__file__).resolve().parents[1] / 'configs'
        examples = sorted(folder.glob('*.json')) + sorted((folder.parent/'tests/worlds').glob('*.json'))
        self.assertTrue(examples)
        for source in examples:
            overrides = json.loads(source.read_text())
            for domain in scenario.delivery_data.DOMAINS:
                fingerprints = []
                for preset in scenario.PRESETS:
                    with self.subTest(config=source.name, domain=domain, preset=preset):
                        manifest, _ = preview.build_preview(domain, preset, overrides)
                        fingerprints.append(manifest['input_contract']['subject_sha256'])
                self.assertTrue(all(row == fingerprints[0] for row in fingerprints),
                                (source.name, domain))

    def test_all_domain_presets_keep_the_registration_contract_without_launching_anything(self):
        with patch('socket.socket', side_effect=AssertionError('network attempt')), \
             patch('subprocess.Popen', side_effect=AssertionError('process attempt')):
            for domain in scenario.delivery_data.DOMAINS:
                fingerprints = []
                for preset in scenario.PRESETS:
                    manifest, subjects = preview.build_preview(domain, preset)
                    contract = manifest['input_contract']
                    self.assertEqual(manifest['entrypoint'], {
                        'study_mode': 'unified',
                        'component_family': scenario.FAMILY,
                    })
                    world_config.verify_input_contract(manifest['assignments'], contract)
                    self.assertEqual({name: scenario.digest(value) for name, value in subjects.items()},
                                     contract['subject_sha256'])
                    self.assertFalse(manifest['communication_start']['peer_roster_supplied'])
                    self.assertFalse(manifest['communication_start']['dedicated_communication_tools'])
                    self.assertTrue(all('/workspace/communications.json' not in files
                                        for files in subjects['initial_files'].values()))
                    fingerprints.append(contract['subject_sha256'])
                self.assertTrue(all(row == fingerprints[0] for row in fingerprints))

    def test_cli_exports_exact_readable_bytes_and_never_overwrites_a_prior_preview(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / 'preview'
            args = ['--scenario', 'data-analysis', '--binding-preset', 'control', '--output', str(output)]
            with patch('socket.socket', side_effect=AssertionError('network attempt')), \
                 patch('subprocess.Popen', side_effect=AssertionError('process attempt')):
                preview.main(args)
            raw = json.loads((output / 'subject-inputs.json').read_text())
            for actor, files in raw['initial_files'].items():
                self.assertEqual((output / f'tasks/{actor}.txt').read_bytes(), raw['tasks'][actor].encode())
                for name, content in files.items():
                    self.assertEqual((output / 'workstations' / actor / name.lstrip('/')).read_bytes(),
                                     base64.b64decode(content))
            self.assertEqual(json.loads((output / 'tools.json').read_text()), raw['tools'])
            before = {p.relative_to(output): p.read_bytes() for p in output.rglob('*') if p.is_file()}
            with self.assertRaises(SystemExit), patch('sys.stderr'):
                preview.main(args)
            self.assertEqual(before, {p.relative_to(output): p.read_bytes()
                                      for p in output.rglob('*') if p.is_file()})
            self.assertEqual(json.loads((output / 'manifest.json').read_text())['validation'],
                             {'input_contract': 'passed', 'execution_paths': 'not_run',
                              'model_behavior': 'not_tested'})

    def test_invalid_or_mismatched_configuration_creates_no_preview(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            config, output = folder / 'world.json', folder / 'preview'
            for bad in ({'typo': {}}, {'verification': {'capacity_basis': 'unknown'}},
                        {'verification': {'capacity_basis': 'forecast'}}):
                config.write_text(json.dumps(bad))
                with self.assertRaises(SystemExit), patch('sys.stderr'):
                    preview.main(['--world-config', str(config), '--output', str(output)])
                self.assertFalse(output.exists())

    def test_out_of_workspace_material_is_rejected_before_any_files_are_written(self):
        manifest, subjects = preview.build_preview('knowledge-work', 'control')
        damaged = deepcopy(subjects)
        damaged['initial_files'][preview.ACTORS[0]]['/workspace/../../outside'] = 'eA=='
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / 'preview'
            with self.assertRaisesRegex(ValueError, 'outside the business workspace'):
                preview.write_preview(output, manifest, damaged)
            self.assertFalse(output.exists())
