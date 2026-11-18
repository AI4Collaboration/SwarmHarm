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

    def test_routed_bundle_preserves_source_bytes_at_one_other_account(self):
        from phase2 import delivery_source_routing, workload_sources
        exports = {'Meridian': 'routed_bundle', 'Harbor': 'routed_bundle'}
        config = {'coupling': {'source_routing': delivery_source_routing.CROSS_ACCOUNT_RING},
                  'access': {'source_record_counts': {'Meridian': 12}}}
        plain = self.plan(overrides=config)
        config['access']['source_exports'] = exports
        routed = self.plan(overrides=config)
        baseline = {a: scenario.documents(row) for a, row in plain.items()}
        files = {a: scenario.documents(row) for a, row in routed.items()}
        for owner, row in routed.items():
            self.assertEqual(scenario.task(row), scenario.task(plain[owner]))
            if row['account'] not in exports:
                continue
            request = delivery_source_routing.request_reference(row)
            prefix = f'source-routing/outbox/{request}/'
            holders = [a for a in files if prefix + 'source-data.json' in files[a]]
            self.assertEqual(len(holders), 1)
            holder, = holders
            self.assertNotEqual(owner, holder)
            self.assertEqual(files[holder][prefix + 'source-data.json'], baseline[owner]['source-data.json'])
            raw = scenario.delivery_data.source_bundle(row)
            self.assertTrue(raw.keys().isdisjoint(files[owner]))
            self.assertEqual(json.loads(files[owner]['source-export.json'])['included_objects'], [])
            received = {k[len(prefix):]: v for k, v in files[holder].items()
                        if k.startswith(prefix) and k != prefix + 'source-data.json'}
            self.assertEqual(received, raw)
            domain = scenario.delivery_data.domain_for(row)
            self.assertEqual(sorted(workload_sources.reduce_sources(domain, received)),
                             sorted(scenario.delivery_data.reference_data(row)['rows']))
        with self.assertRaisesRegex(ValueError, 'require cross-account'):
            scenario.normalize_config({'access': {'source_exports': exports}})

    def test_staged_drafts_only_add_the_build_files(self):
        plain = self.plan()
        staged = self.plan(overrides={'access': {'report_drafts': {
            'Northline': 'staged', 'Aster': 'staged'}}})
        announced = self.plan(overrides={'access': {'report_drafts': {
            'Northline': 'current', 'Aster': 'current'}}})
        for actor, row in staged.items():
            baseline = scenario.documents(plain[actor])
            files = scenario.documents(row)
            self.assertEqual(scenario.task(row), scenario.task(plain[actor]))
            self.assertEqual({k: files[k] for k in baseline}, baseline)
            added = set(files) - set(baseline)
            if row['account'] in ('Northline', 'Aster'):
                expected = {f'report-drafts/{item}.csv' for item in scenario.ITEMS}
                self.assertEqual(added, expected | {'report-drafts/manifest.json'})
                announced_files = scenario.documents(announced[actor])
                self.assertEqual({k: files[k] for k in added}, {k: announced_files[k] for k in added})
                self.assertNotEqual(announced_files['work-order.json'], files['work-order.json'])
            else:
                self.assertEqual(added, set())

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
        folder = Path(__file__).resolve().parent / 'worlds'
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
