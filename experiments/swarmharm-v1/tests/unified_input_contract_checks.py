"""One common input, separately selected interfaces and separately sealed runs."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from phase2 import unified_delivery as scenario, world_config
from tests import delivery_path_checks as fixtures


class UnifiedInputContractChecks(unittest.TestCase):
    plan = fixtures.DeliveryPathChecks.plan

    def test_each_preset_is_independent_with_identical_subject_bytes_in_all_domains(self):
        for domain in scenario.delivery_data.DOMAINS:
            for basis in ('dispatch', 'contents', 'handoff'):
                fingerprints = []
                for preset in scenario.PRESETS:
                    plan = self.plan(preset, {'verification': {'completion_basis': basis}}, domain)
                    contract = world_config.input_contract(plan)
                    fingerprints.append(contract['subject_sha256'])
                    chosen = contract['selection']
                    self.assertTrue(chosen['matches_named_preset'])
                    self.assertEqual(chosen['mode'], 'baseline' if preset == 'control' else 'single')
                    self.assertEqual(len(chosen['changed_bindings']), 0 if preset == 'control' else 1)
                    world_config.verify_input_contract(plan, contract)
                self.assertTrue(all(row == fingerprints[0] for row in fingerprints))

    def test_mixed_bindings_need_explicit_combination_without_changing_subject_inputs(self):
        plan = self.plan('trace', {'verification': {'grader_source': 'workspace'},
                                  'access': {'information_scope': 'account'}})
        with self.assertRaisesRegex(ValueError, '--combined-bindings'):
            world_config.input_contract(plan)
        combined = world_config.input_contract(plan, combined=True)
        self.assertEqual(combined['selection']['mode'], 'combined')
        self.assertEqual(len(combined['selection']['changed_bindings']), 3)
        self.assertFalse(combined['selection']['matches_named_preset'])
        single = world_config.input_contract(self.plan('trace'))
        self.assertEqual(combined['subject_sha256'], single['subject_sha256'])
        world_config.verify_input_contract(plan, combined)
        with self.assertRaisesRegex(ValueError, 'at least two'):
            world_config.input_contract(self.plan('grader'), combined=True)

    def test_binding_specific_prompt_or_file_leak_is_rejected(self):
        plan = self.plan('grader')
        original = scenario.task
        with patch.object(scenario, 'task', lambda row: original(row) + row['binding_preset']):
            with self.assertRaisesRegex(ValueError, 'shared subject inputs'):
                world_config.input_contract(plan)

    def test_full_world_cannot_silently_replace_the_named_interface(self):
        # A copied complete grader config overrides all inherited trace defaults.
        world = world_config.normalize(preset='grader')
        plan = self.plan('trace', world)
        with self.assertRaisesRegex(ValueError, 'selected preset'):
            world_config.input_contract(plan)

    def test_modified_domain_condition_or_fingerprint_cannot_reuse_a_registration(self):
        plan = self.plan('records')
        registered = world_config.input_contract(plan)
        for changed in (self.plan('records', domain='financial-analysis'),
                        self.plan('records', {'observation': {'feedback': 'provenance'}}),
                        self.plan('grader')):
            with self.assertRaises(ValueError):
                world_config.verify_input_contract(changed, registered)
        damaged = deepcopy(registered)
        damaged['subject_sha256']['tasks'] = '0' * 64
        with self.assertRaises(ValueError):
            world_config.verify_input_contract(plan, damaged)
        with self.assertRaises(ValueError):
            world_config.verify_input_contract(plan, None)

    def test_successful_settings_do_not_require_combining_threat_models(self):
        folder = Path(__file__).resolve().parents[1] / 'configs'
        for name, preset in (
                ('unified-report-uploads.json', 'records'),
                ('unified-shared-headroom.json', 'resource'),
                ('unified-delayed-account-view.json', 'control')):
            plan = self.plan(preset, json.loads((folder / name).read_text()))
            before = deepcopy(plan), scenario.initial_files(plan)
            contract = world_config.input_contract(plan)
            self.assertFalse(contract['selection']['combination_explicit'])
            self.assertEqual(before, (plan, scenario.initial_files(plan)))


if __name__ == '__main__':
    unittest.main()
