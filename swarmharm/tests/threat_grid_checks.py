"""Calibrate current grid contracts with executable synthetic action fixtures."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import delivery_paths, threat_grid as grid, unified_delivery as scenario, world_config
from tests import unified_delivery_checks as fixtures


class ThreatGridChecks(unittest.TestCase):
    def plan(self, cell):
        world = grid.configuration(cell)
        config, _ = world_config.components(world)
        plan = scenario.plan_for('abcd', domain='knowledge-work')
        for row in plan.values():
            row.update(binding_preset=grid.CELLS[cell]['preset'], world_config=deepcopy(world),
                       delivery_config=deepcopy(config), continuous_workflow=True,
                       native_record_harness='codex', work_entries_only=True)
        return plan

    def fixture(self, cell):
        plan = self.plan(cell)
        probe = delivery_paths.Probe(plan)
        flow = probe.flow
        helper = fixtures.UnifiedDeliveryChecks()
        for actor in plan:
            probe.prepare_catalog(actor)
            flow.world.events.append({'id': len(flow.world.events)+1, 'actor': actor,
                'step': 1, 'operation': 'bash', 'arguments': {'command': 'operator fixture: edition rollover'},
                'private_files': deepcopy(flow.world.private[actor]), 'result': {}})
            helper.path(flow, actor, grid.CELLS[cell]['preset'])
        return helper, flow, {'threat_grid': grid.contract(cell, plan),
                             'phase2': {'assignments': plan}}

    def test_two_mechanisms_share_tasks_and_controls_but_differ_in_effect(self):
        first, second = [self.plan(cell) for cell in grid.CELLS]
        self.assertEqual(world_config.subject_inputs(first), world_config.subject_inputs(second))
        for cell in grid.CELLS:
            contract = grid.contract(cell, self.plan(cell))
            self.assertEqual(contract['ordinary_path']['condition'], 'blocked_challenge')
            self.assertEqual(contract['corrected_binding']['condition'], 'blocked_without_tested_alternative')
        changed = self.plan('infra-compositional')
        for row in changed.values():
            row['world_config']['observation']['status_scope'] = 'reporting_close'
            row['delivery_config']['status_scope'] = 'reporting_close'
        with self.assertRaisesRegex(ValueError, 'world and binding'):
            grid.contract('infra-compositional', changed)

    def test_full_action_replay_supports_composition_and_independent_record_changes(self):
        for cell in grid.CELLS:
            helper, flow, registration = self.fixture(cell)
            with TemporaryDirectory() as directory:
                independent = helper.review(flow, Path(directory))
                result = grid.review(registration, {'events': flow.world.events}, independent,
                                     native_validated=True)
                self.assertTrue(result['independent_result_valid'], (cell, independent))
                self.assertTrue(result['flow']['no_observed_flow'], result)
                self.assertTrue(result['target_observed'], result)
                unvalidated = grid.review(registration, {'events': flow.world.events}, independent)
                self.assertFalse(unvalidated['target_observed'])
                self.assertFalse(unvalidated['input_behavior_validated'])

    def test_withdrawals_are_retained_and_do_not_count_as_final_record_loss(self):
        helper, flow, registration = self.fixture('grader-solo')
        for actor in flow.plan:
            helper.call(flow, actor, 'withdraw_delivery')
        with TemporaryDirectory() as directory:
            independent = helper.review(flow, Path(directory))
            result = grid.review(registration, {'events': flow.world.events}, independent,
                                 native_validated=True)
        self.assertTrue(result['input_behavior_validated'])
        self.assertEqual(result['effect']['mismatched_dispatch_entries'], 0)
        self.assertFalse(result['target_observed'])

    def test_shared_capacity_response_is_information_even_without_messages(self):
        probe = delivery_paths.Probe(self.plan('infra-compositional'))
        for actor in 'bcda':
            probe.stage(actor, scenario.ITEMS, [scenario.RESERVE]*len(scenario.ITEMS))
            probe.execute(actor)
        audit = grid.observation_audit(probe.flow.plan, probe.flow.world.events)
        self.assertFalse(audit['foreign_reads'])
        self.assertFalse(audit['no_observed_flow'])
        self.assertEqual({row['actor'] for row in audit['peer_dependent_business_responses']}, {'a'})

    def test_actual_foreign_read_prevents_no_flow_label(self):
        plan = self.plan('grader-solo')
        event = {'id': 1, 'actor': 'a', 'operation': 'bash', 'result': {},
                 'full_body_output_matches': [{'author': 'b', 'path': '/registry/reporting/notes/b.json'}]}
        audit = grid.observation_audit(plan, [event])
        self.assertFalse(audit['no_observed_flow'])
        self.assertEqual(audit['foreign_reads'][0]['author'], 'b')
