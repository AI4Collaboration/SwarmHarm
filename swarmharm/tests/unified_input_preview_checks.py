"""Reviewable business-input export without starting an evaluation."""
import base64
from copy import deepcopy
import importlib.util
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import office_history, unified_delivery as scenario, world_config

SCRIPT = Path(__file__).resolve().parents[2] / 'swarmharm/scripts/inspect_unified_input.py'
SPEC = importlib.util.spec_from_file_location('inspect_unified_input', SCRIPT)
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)


class UnifiedInputPreviewChecks(unittest.TestCase):
    def test_knowledge_work_groups_analytical_workloads_without_changing_subjects(self):
        for workload in ('data-analysis', 'financial-analysis'):
            with self.subTest(workload=workload), TemporaryDirectory() as folder:
                manifest, subjects = preview.build_preview('knowledge-work', 'resource', workload=workload)
                _, original = preview.build_preview(workload, 'resource')
                self.assertEqual(subjects, original)
                self.assertEqual(manifest['domain'], 'knowledge-work')
                self.assertEqual(manifest['workload'], workload)
                self.assertTrue(all(row['delivery_domain'] == workload for row in manifest['assignments'].values()))
                output = Path(folder)/'export'
                preview.main(['--scenario', 'knowledge-work', '--workload', workload,
                              '--binding-preset', 'resource', '--output', str(output)])
                self.assertEqual(json.loads((output/'subject-inputs.json').read_text()), subjects)
                with self.assertRaises(ValueError):
                    preview.build_preview('engineering-capacity', 'resource', workload=workload)

    def test_current_domain_selector_excludes_separate_analytical_domains(self):
        for args in (['--scenario', 'data-analysis'], ['--scenario', 'financial-analysis'],
                     ['--scenario', 'all', '--workload', 'data-analysis', '--mechanism', 'implemented']):
            with self.subTest(args=args), TemporaryDirectory() as folder, patch('sys.stderr'):
                output = Path(folder)/'invalid'
                with self.assertRaises(SystemExit):
                    preview.main([*args, '--output', str(output)])
                self.assertFalse(output.exists())


    def test_prior_office_work_adds_only_private_files_to_the_frozen_formation_inputs(self):
        import run
        self.assertIn(office_history.ARCHIVE, run.code_paths())
        base = json.loads((run.HERE/'tests/worlds/unified-cross-account-source-routing.json').read_bytes())
        _, original = preview.build_preview('knowledge-work', 'records', base)
        config = deepcopy(base)
        config['observation'][office_history.FIELD] = office_history.TASK_ONLY
        _, clean = preview.build_preview('knowledge-work', 'records', config)
        self.assertEqual(original, clean)
        config['observation'][office_history.FIELD] = office_history.PRIOR_WORK
        manifest, used = preview.build_preview('knowledge-work', 'records', config)
        for field in ('tasks', 'tools', 'business_data'):
            self.assertEqual(original[field], used[field])
        with TemporaryDirectory() as folder:
            output = Path(folder)/'export'
            preview.write_preview(output, manifest, used)
            unique_downloads = set()
            for actor, docs in used['initial_files'].items():
                existing = original['initial_files'][actor]
                self.assertEqual({p: docs[p] for p in existing}, existing)
                self.assertEqual(set(docs) - set(existing), set(office_history.MTIMES))
                paths = office_history.PATHS
                def read(name):
                    return (output/'workstations'/actor/paths[name].lstrip('/')).read_bytes()
                self.assertEqual(read('download.csv'), read('shelf-count.csv~'))
                self.assertNotEqual(read('shelf-count.csv'), read('shelf-count.csv~'))
                self.assertTrue(read('shelf-count.pdf').startswith(b'%PDF-'))
                self.assertIn(office_history.URI.encode(), read('thumbnail.png'))
                unique_downloads.add(read('download.csv'))
            self.assertEqual(len(unique_downloads), 3)

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
            actors = None
            if overrides.get('coupling', {}).get('completion_credit') == 'reporting_desk':
                actors = scenario.cohort.actor_ids(4)
                with self.assertRaisesRegex(ValueError, 'two account owners'):
                    preview.build_preview('knowledge-work', 'control', overrides,
                                          actors=scenario.cohort.actor_ids(3))
            for domain in scenario.delivery_data.DOMAINS:
                fingerprints = []
                for preset in scenario.PRESETS:
                    with self.subTest(config=source.name, domain=domain, preset=preset):
                        # A complete world can pin bindings that a different preset would change.
                        world = world_config.normalize(overrides, preset=preset)
                        _, bindings = world_config.components(world)
                        if bindings != scenario.PRESETS[preset]:
                            with self.assertRaisesRegex(ValueError, 'selected preset|Multiple evaluated bindings'):
                                preview.build_preview(domain, preset, overrides, actors=actors)
                            continue
                        manifest, _ = preview.build_preview(domain, preset, overrides, actors=actors)
                        fingerprints.append(manifest['input_contract']['subject_sha256'])
                self.assertTrue(fingerprints, source.name)
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
            args = ['--scenario', 'knowledge-work', '--workload', 'data-analysis',
                    '--binding-preset', 'control', '--output', str(output)]
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

    def test_markdown_export_checks_sealed_bytes_and_offers_current_preview(self):
        cmd = [sys.executable, str(SCRIPT.with_name('dump_prompts.py'))]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            current = root/'current'
            subprocess.run([*cmd, '--output', str(current)], check=True, capture_output=True)
            self.assertEqual(len(list(current.glob('job-*.md'))), 3)
            self.assertIn('Do not ask the user', (current/'job-faraday.md').read_text())
            self.assertIn('submit_report', (current/'job-faraday.md').read_text())
            self.assertIn('preview_commit', (current/'README.md').read_text())

            reg = root/'case'
            reg.mkdir()
            def store(name, obj):
                data = json.dumps(obj).encode()
                (reg/name).write_bytes(data)
                return sha256(data).hexdigest()
            audit = {a: {'instructions': 'Recorded instructions', 'input': [
                     {'role': 'user', 'content': 'Recorded request'}], 'tools': []} for a in preview.ACTORS}
            files = {a: {'/workspace/a.md': base64.b64encode(b'adapted text').decode()} for a in audit}
            hashes = {n: store(n, {'natural': rows}) for n, rows in
                      [('initial-input-audit.json', audit), ('initial-file-audit.json', files)]}
            seal = store('registration.json', {'study_mode': 'unified', 'scenario': 'knowledge-work',
                'phase2': {'component_family': 'unified-delivery', 'binding_preset': 'records'},
                'models': {'sol': 'example'}, 'harness': {'kind': 'codex', 'goal_mode': 'off'},
                'completion_protocol': {}, 'input_hashes': hashes})
            store('registration-seal.json', {'sha256': seal})
            sealed = root/'sealed'
            subprocess.run([*cmd, '--registration-dir', str(reg), '--output', str(sealed)],
                           check=True, capture_output=True)
            text = (sealed/'job-faraday.md').read_text()
            for original in ('Recorded instructions', 'Recorded request', 'adapted text'):
                self.assertIn(original, text)
            self.assertIn(seal, (sealed/'README.md').read_text())
            store('initial-file-audit.json', {})
            refused = subprocess.run([*cmd, '--registration-dir', str(reg), '--output', str(root/'invalid')],
                                     capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn('Sealed input differs', refused.stderr)
            self.assertFalse((root/'invalid').exists())

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
