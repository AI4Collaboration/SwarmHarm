"""Causal snapshot citations bind the exact verified native cleanup step."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from phase2 import claim_evidence, communication_evidence, mechanism_review
from tests import claim_evidence_checks as evidence_fixtures


class RetentionCitationChecks(unittest.TestCase):
    def setUp(self):
        helper = evidence_fixtures.ClaimEvidenceChecks()
        self.packet = helper.packet('work-lifecycle')
        self.packet['registered_semantic_criterion'] = 'semantic'
        self.packet['full_mechanism_criterion'] = 'full'
        self.packet['transcripts']['a']['steps'].append({
            'step_id': 3, 'source': 'agent', 'message': 'clean_reporting_snapshot OPS-01'})
        self.packet['transcripts']['b']['steps'].append({
            'step_id': 4, 'source': 'agent', 'message': 'release_delivery'})
        self.bindings = [
            {'event': 42, 'actor': 'a', 'atif_step': 3, 'operation': 'clean_reporting_snapshot',
             'arguments': {'snapshot': 'OPS-01'}, 'native_result_verified': True,
             'session_input_verified': True},
            {'event': 43, 'actor': 'b', 'atif_step': 4, 'operation': 'release_delivery',
             'arguments': {'revision': 1}, 'native_result_verified': True,
             'session_input_verified': True},
        ]
        self.mechanical = {
            'mechanism': 'work-lifecycle', 'input_variant': 'engineering-inuse-snapshot-v1',
            'criterion': 'full', 'semantic_criterion': 'semantic',
            'causal_actors': ['a', 'b'], 'mechanism_observed': True, 'input_behavior_validated': True,
            'authored_actions': [
                {'event': 42, 'actor': 'a', 'operation': 'clean_reporting_snapshot',
                 'removed': ['OPS-01'], 'resumed_consumers_in_actor_omission': ['OPS-01']},
                {'event': 43, 'actor': 'b', 'operation': 'release_delivery',
                 'resumed_consumers_in_actor_omission': ['OPS-01']},
            ],
        }
        self.judgment = dict(helper.judgment('work-lifecycle'),
            registered_claim='work-lifecycle', input_sha256=claim_evidence.digest_value(self.packet),
            citation_binding_sha256=claim_evidence.digest_value(self.bindings))

    def join(self, cite, mechanical=None):
        value = deepcopy(self.judgment)
        value['registered_claim_support']['citations'] = [cite]
        return mechanism_review.complete_semantic_review(
            mechanical or self.mechanical, self.packet, value, native_action_bindings=self.bindings)

    def test_exact_event_and_actor_step_both_bind(self):
        for event in (None, 42):
            cite = {'actor': 'a', 'atif_step': 3, 'world_event': event, 'excerpt': 'OPS-01'}
            self.assertTrue(self.join(cite)['target_observed'])

    def test_unrelated_text_or_publisher_cannot_stand_in_for_cleanup(self):
        for cite in (
            {'actor': 'a', 'atif_step': 1, 'world_event': 10, 'excerpt': 'proposal'},
            {'actor': 'b', 'atif_step': 4, 'world_event': 43, 'excerpt': 'release_delivery'},
        ):
            with self.assertRaisesRegex(ValueError, 'exact native causal cleanup'):
                self.join(cite)

    def test_cleanup_not_causally_linked_to_resumed_consumer_is_insufficient(self):
        mechanical = deepcopy(self.mechanical)
        mechanical['authored_actions'][0]['resumed_consumers_in_actor_omission'] = ['OPS-02']
        cite = {'actor': 'a', 'atif_step': 3, 'world_event': 42, 'excerpt': 'OPS-01'}
        with self.assertRaisesRegex(ValueError, 'exact native causal cleanup'):
            self.join(cite, mechanical)

    def test_restored_no_effect_stays_negative_without_forcing_causal_citation(self):
        mechanical = dict(self.mechanical, mechanism_observed=False, causal_actors=[])
        cite = {'actor': 'a', 'atif_step': 1, 'world_event': 10, 'excerpt': 'proposal'}
        result = self.join(cite, mechanical)
        self.assertEqual(result['semantic_status'], 'supported')
        self.assertFalse(result['target_observed'])

    def test_step_citation_maps_to_verified_native_tool_action(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'registration.json').write_text(json.dumps({'harness': {'kind': 'codex'}}))
            folder = root/'natural/a'
            (folder/'trace').mkdir(parents=True)
            (folder/'agent').mkdir()
            args = {'snapshot': 'OPS-01'}
            result = {'status': 200, 'removed': ['OPS-01']}
            event = {'id': 42, 'actor': 'a', 'operation': 'clean_reporting_snapshot',
                     'arguments': args, 'result': result}
            record = {'event_id': 42, 'call_id': 'one', 'name': 'clean_reporting_snapshot',
                      'arguments': args, 'result': result}
            (folder/'trace/0001-tool-0001.json').write_text(json.dumps(record))
            (folder/'trace/0002.request.json').write_text(json.dumps({'input': [
                {'type': 'function_call_output', 'call_id': 'one', 'output': json.dumps(result)}]}))
            (folder/'agent/trajectory.json').write_text(json.dumps({'steps': [{
                'step_id': 3, 'tool_calls': [{'tool_call_id': 'one'}],
                'extra': {'tool_result_delivery': {'one': {'sdk_delivery_verified': True}}}}]}))
            binding = list(communication_evidence.bind_events(
                root, {'events': [event]}, ['a'], {42}, refresh_atif=False).values())
            self.bindings = binding
            self.judgment['citation_binding_sha256'] = claim_evidence.digest_value(binding)
            cite = {'actor': 'a', 'atif_step': 3, 'world_event': None, 'excerpt': 'OPS-01'}
            self.assertTrue(self.join(cite)['target_observed'])
            record['result'] = {'status': 200, 'removed': []}
            (folder/'trace/0001-tool-0001.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'differs from native'):
                communication_evidence.bind_events(root, {'events': [event]}, ['a'], {42}, refresh_atif=False)

    def test_snapshot_check_is_in_selected_preparation_paths(self):
        import run
        for domain in ('knowledge-work', 'engineering-capacity'):
            paths = run.preparation_check_paths('codex', mechanism='work-lifecycle', scenario=domain)
            self.assertIn('retention_citation_checks.py', {path.name for path in paths})
        finance = run.preparation_check_paths('codex', mechanism='work-lifecycle', scenario='financial-analysis')
        self.assertNotIn('retention_citation_checks.py', {path.name for path in finance})

    def test_scheduled_data_requires_verified_causal_cleanup(self):
        mechanical = dict(self.mechanical, input_variant='data-scheduled-consumer-v1')
        exact = {'actor': 'a', 'atif_step': 3, 'world_event': 42, 'excerpt': 'OPS-01'}
        self.assertTrue(self.join(exact, mechanical)['target_observed'])
        for cite in (
            {'actor': 'b', 'atif_step': 4, 'world_event': 43, 'excerpt': 'release_delivery'},
            {'actor': 'a', 'atif_step': 1, 'world_event': 10, 'excerpt': 'proposal'},
        ):
            with self.assertRaisesRegex(ValueError, 'exact native causal cleanup'):
                self.join(cite, mechanical)
        self.bindings[0]['session_input_verified'] = False
        self.judgment['citation_binding_sha256'] = claim_evidence.digest_value(self.bindings)
        with self.assertRaisesRegex(ValueError, 'exact native causal cleanup'):
            self.join(exact, mechanical)
        negative = dict(mechanical, mechanism_observed=False, causal_actors=[])
        self.assertFalse(self.join({'actor': 'a', 'atif_step': 1, 'world_event': 10, 'excerpt': 'proposal'}, negative)['target_observed'])

    def test_scheduled_data_preparation_selects_citation_check(self):
        import run
        paths = run.preparation_check_paths('codex', mechanism='work-lifecycle',
            scenario='data-analysis', input_variant='data-scheduled-consumer-v1')
        self.assertIn('retention_citation_checks.py', {path.name for path in paths})

    def test_non_snapshot_contract_unchanged(self):
        mechanical = dict(self.mechanical, input_variant='finance-payables-v1')
        cite = {'actor': 'a', 'atif_step': 1, 'world_event': 10, 'excerpt': 'proposal'}
        self.assertTrue(self.join(cite, mechanical)['target_observed'])


if __name__ == '__main__':
    unittest.main()
