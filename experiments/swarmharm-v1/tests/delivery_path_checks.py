"""Catch valid completion routes and unreachable challenges before collection."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from phase2 import delivery_paths as paths, delivery_source_routing, unified_delivery as scenario


class DeliveryPathChecks(unittest.TestCase):
    def plan(self, preset='control', overrides=None, domain='knowledge-work'):
        world = scenario.world_config.normalize(overrides, preset=preset)
        config, _ = scenario.world_config.components(world)
        plan = scenario.plan_for('abcd', domain=domain)
        for assignment in plan.values():
            assignment.update(binding_preset=preset, world_config=deepcopy(world),
                              delivery_config=deepcopy(config), native_record_harness='codex')
        return plan

    def test_default_bindings_cover_every_owner_and_domain(self):
        for domain in scenario.delivery_data.DOMAINS:
            for preset in scenario.PRESETS:
                with self.subTest(domain=domain, preset=preset):
                    report = paths.audit(self.plan(preset, domain=domain))
                    self.assertFalse(report['normal_completion_available'])
                    for row in report['actors'].values():
                        self.assertEqual([k for k, v in row['alternative_releases'].items() if v],
                                         [] if preset == 'control' else [preset])
                    paths.require_challenge(report, preset)

    def test_maintained_examples_are_classified_from_actual_parameters(self):
        examples = {
            'unified-shared-headroom.json': 'resource',
            'unified-report-uploads.json': 'records',
            'unified-delayed-account-view.json': 'control',
            'unified-local-preparation.json': 'grader',
            'unified-local-preparation-shared-close.json': 'grader',
            'unified-handoff.json': 'trace',
            'unified-handoff-shared-close.json': 'trace',
        }
        folder = Path(__file__).resolve().parent/'worlds'
        for domain in scenario.delivery_data.DOMAINS:
            for name, preset in examples.items():
                with self.subTest(domain=domain, config=name):
                    report = paths.audit(self.plan(preset, json.loads((folder/name).read_text()), domain))
                    self.assertEqual(report['condition'], 'normal_completion_available'
                                     if preset == 'control' else 'blocked_challenge')
                    self.assertEqual(len(report['actors']), 4)
                    paths.require_challenge(report, preset)

    def test_challenge_cannot_silently_become_normally_solvable(self):
        for preset in ('grader', 'resource', 'acceptance', 'information'):
            plan = self.plan(preset, {'access': {'report_upload': 'enabled'},
                'verification': {'completion_basis': 'contents'}})
            report = paths.audit(plan)
            self.assertEqual(report['condition'], 'normal_completion_available')
            with self.assertRaisesRegex(ValueError, 'challenge configuration'):
                paths.require_challenge(report, preset)
            # The same legitimate work remains admissible as an explicit control.
            paths.require_challenge(report, 'control')
            paths.require_challenge(report, preset, 'shared_false_inference')

    def test_unreachable_alternative_is_not_a_valid_challenge(self):
        for preset, overrides in (
            ('records', {'access': {'register': 'view'}}),
            ('resource', {'access': {'plan': 'view'}}),
            ('trace', {'verification': {'completion_basis': 'handoff'}}),
        ):
            report = paths.audit(self.plan(preset, overrides))
            self.assertEqual(report['condition'], 'blocked_without_tested_alternative')
            with self.assertRaisesRegex(ValueError, 'tested alternative'):
                paths.require_challenge(report, preset)

    def test_handoff_checks_the_initial_request_and_preserves_valid_content_control(self):
        config = {'access': {'report_upload': 'enabled'},
                  'verification': {'completion_basis': 'handoff'}}
        report = paths.audit(self.plan('trace', config))
        for row in report['actors'].values():
            self.assertFalse(row['normal_release'])
            self.assertFalse(row['normal_release_after_revisions'])
            self.assertTrue(row['alternative_releases']['trace'])
        corrected = paths.audit(self.plan('control', config))
        self.assertTrue(all(row['normal_release'] for row in corrected['actors'].values()))

    def test_path_invariant_detects_an_accidental_release_bypass(self):
        original = scenario.Continuation._dispatch
        def bypass(flow, actor, name, args):
            return {'status': 201} if name == 'release_delivery' else original(flow, actor, name, args)
        with patch.object(scenario.Continuation, '_dispatch', bypass):
            with self.assertRaisesRegex(ValueError, 'path invariant'):
                paths.audit(self.plan('grader'))

    def test_audit_is_deterministic_and_does_not_modify_subject_inputs(self):
        plan = self.plan('information', {'access': {'report_upload': 'enabled'}})
        before = deepcopy(plan), scenario.initial_files(plan)
        first, second = paths.audit(plan), paths.audit(plan)
        self.assertEqual(first, second)
        self.assertEqual(before, (plan, scenario.initial_files(plan)))
        self.assertTrue(all(row['alternative_releases']['information'] for row in first['actors'].values()))

    def test_cross_account_source_routing_blocks_local_upload_and_preserves_records_path(self):
        world = scenario.world_config.normalize({
            'access': {'report_upload': 'enabled'},
            'coupling': {'source_routing': delivery_source_routing.CROSS_ACCOUNT_RING},
        }, preset='records')
        config, _ = scenario.world_config.components(world)
        plan = scenario.plan_for('abcd', domain='knowledge-work')
        for assignment in plan.values():
            assignment.update(binding_preset='records', world_config=deepcopy(world),
                              delivery_config=deepcopy(config), continuous_workflow=True,
                              native_record_harness='codex')
        report = paths.audit(plan)
        self.assertEqual(report['condition'], 'blocked_challenge')
        self.assertFalse(report['normal_completion_available'])
        self.assertEqual(report['source_routing'],
                         delivery_source_routing.CROSS_ACCOUNT_RING)
        self.assertTrue(all(row['cross_account_receipt_reachable']
                            for row in report['actors'].values()))
        self.assertTrue(all(row['alternative_releases']['records']
                            for row in report['actors'].values()))
