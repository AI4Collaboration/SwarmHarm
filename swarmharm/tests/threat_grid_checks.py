"""Calibrate current grid contracts with executable synthetic action fixtures."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import json
import unittest

from phase2 import delivery_paths, threat_grid as grid, unified_delivery as scenario, world_config
from tests import unified_delivery_checks as fixtures
from tests import claim_evidence_checks as semantic_fixtures
from phase2 import claim_evidence
from phase1 import lab


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
        first, second = [self.plan(cell) for cell in ('infra-compositional', 'grader-solo')]
        self.assertEqual(world_config.subject_inputs(first), world_config.subject_inputs(second))
        for cell in ('infra-compositional', 'grader-solo'):
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
        for cell in ('infra-compositional', 'grader-solo'):
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

    def test_all_nine_inputs_have_path_and_bound_control_contracts(self):
        self.assertEqual(len(grid.CELLS), 9)
        self.assertEqual(len({row['id'] for row in grid.CELLS.values()}), 9)
        for cell, definition in grid.CELLS.items():
            plan = self.plan(cell)
            contract = grid.contract(cell, plan)
            self.assertEqual(contract, grid.contract(cell, plan))
            self.assertEqual(world_config.input_contract(plan)['matched_baseline_subject_inputs'], True)
            if definition['flow'] == 'one_way':
                self.assertEqual(contract['ordinary_path']['condition'], 'mixed_solvability')
                self.assertTrue(contract['note_exposure']['passed'])
                self.assertEqual(contract['source_actor'], 'a')
            self.assertEqual(world_config.components(grid.configuration(cell))[0],
                             scenario.config_for(plan))

    def notes(self, reads):
        events, records = [], {}
        for index, (author, reader) in enumerate(reads):
            path = grid.delivery_notes.ROOT + '/' + str(index) + '.json'
            body = json.dumps({'record_type': 'reporting_note',
                'account': scenario.ACCOUNTS['abcd'.index(author)],
                'text': 'Operator fixture with exact authored content '+str(index)}).encode()
            record = {'path': path, 'author': author, 'origin': 'bash',
                      'data': base64.b64encode(body).decode(),
                      'sha256': scenario.sha256(body).hexdigest()}
            events.append({'id': len(events)+1, 'step': len(events)+1, 'actor': author,
                'operation': 'bash', 'result': {}, 'shared_changes': [record]})
            records[path] = record
            result = {'status': 200, 'stdout': body.decode()}
            matches = lab.shared_output_reads(records.values(), reader, result)
            events.append({'id': len(events)+1, 'step': len(events)+1, 'actor': reader,
                'operation': 'bash', 'result': result, **matches})
        return events

    def test_direction_needs_delivered_reads_not_writes_or_parallel_actions(self):
        plan = self.plan('grader-cascade')
        events = self.notes([('a', 'b'), ('a', 'c')])
        one = grid.directed_flow(plan, events, grid.CELLS['grader-cascade'])
        self.assertTrue(one['condition_matched'], one)
        self.assertFalse(one['reciprocal_path_observed'])
        self.assertFalse(grid.directed_flow(plan, events, grid.CELLS['grader-coordinated'])['condition_matched'])
        back = self.notes([('a', 'b'), ('b', 'a')])
        self.assertFalse(grid.directed_flow(plan, back, grid.CELLS['grader-cascade'])['condition_matched'])
        self.assertTrue(grid.directed_flow(plan, back, grid.CELLS['grader-coordinated'])['condition_matched'])
        for event in back:
            event.pop('full_body_output_matches', None)
            event.pop('message_body_output_matches', None)
        self.assertFalse(grid.directed_flow(plan, back, grid.CELLS['grader-coordinated'])['condition_matched'])

    def test_semantic_support_cannot_substitute_for_final_effect_or_exact_flow(self):
        cell = 'grader-coordinated'
        helper = semantic_fixtures.ClaimEvidenceChecks()
        packet = helper.packet(cell)
        packet['registered_semantic_criterion'] = grid.CELLS[cell]['criterion']
        judgment = claim_evidence.transcript_judgment(packet, helper.judgment(cell), model='judge-fixture')
        mechanical = {'cell': cell, 'input_behavior_validated': True,
                      'flow': {'condition_matched': True}, 'mechanism_observed': True}
        self.assertTrue(grid.complete_semantic_review(mechanical, packet, judgment)['target_observed'])
        for field in ('input_behavior_validated', 'mechanism_observed'):
            self.assertFalse(grid.complete_semantic_review(
                {**mechanical, field: False}, packet, judgment)['target_observed'])
        self.assertFalse(grid.complete_semantic_review(
            {**mechanical, 'flow': {'condition_matched': False}}, packet, judgment)['target_observed'])
        with self.assertRaises(ValueError):
            grid.complete_semantic_review(mechanical, packet, {**judgment, 'input_sha256': '0'*64})
        unsupported = deepcopy(judgment)
        unsupported['registered_claim_support']['status'] = 'not_supported'
        self.assertFalse(grid.complete_semantic_review(mechanical, packet, unsupported)['target_observed'])
        only_one = deepcopy(judgment)
        only_one['registered_claim_support']['citations'] = only_one['registered_claim_support']['citations'][:1]
        with self.assertRaises(ValueError):
            grid.complete_semantic_review(mechanical, packet, only_one)
