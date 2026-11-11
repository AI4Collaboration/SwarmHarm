"""Final effects and corrections, exercised through the actual reporting service."""
import json
from pathlib import Path
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest

from phase2 import claim_evidence, delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as scenario
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as delivery_fixtures
from tests import claim_evidence_checks as evidence_fixtures


class MechanismReviewChecks(unittest.TestCase):
    def fixture(self, mechanism):
        manifest, _ = build_preview('knowledge-work', mechanism_inputs.MECHANISMS[mechanism]['preset'],
                                     mechanism=mechanism)
        plan = manifest['assignments']
        reg = {'phase2': {'assignments': plan},
               'mechanism_contract': mechanism_inputs.validate_paths(mechanism, plan)}
        probe = delivery_paths.Probe(plan)
        helpers = delivery_fixtures.UnifiedDeliveryChecks()
        for actor in plan:
            probe.prepare_catalog(actor)
            path = scenario.release_policy.selected_path(probe.flow.world.private[actor],
                                                        probe.flow.config['descriptor_delivery'])
            text = scenario.release_policy.workspace_text(probe.flow.world.private[actor], path)
            helpers.set_policy(probe.flow, actor, text, path)
            if mechanism == 'information-authority':
                read = helpers.library_read(probe.flow, actor, 'assurance')
                probe.call(actor, 'import_reporting_pack', read_receipt=read['result']['read_receipt'])
                self.assertEqual(probe.release(actor)['status'], 201)
                continue
            probe.ordinary(actor)
            if mechanism == 'shared-capacity':
                self.assertEqual(probe.release(actor)['status'], 201)
            elif mechanism == 'grader-tampering':
                policy = json.loads(text)
                policy['properties']['missing_items']['maxItems'] = len(scenario.ITEMS)
                helpers.set_policy(probe.flow, actor, json.dumps(policy), path)
                self.assertEqual(probe.release(actor)['status'], 201)
            else:
                self.assertTrue(probe.alternative(actor, mechanism_inputs.MECHANISMS[mechanism]['preset']))
        return probe, helpers, reg

    def test_actual_publications_and_corrected_full_action_replays(self):
        for mechanism in mechanism_inputs.implemented():
            with self.subTest(mechanism=mechanism), TemporaryDirectory() as directory:
                probe, helpers, reg = self.fixture(mechanism)
                root = Path(directory)
                independent = helpers.review(probe.flow, root)
                world = {'events': probe.flow.world.events}
                result = mechanism_review.review(reg, world, independent, root/'natural', native_validated=True)
                self.assertTrue(result['independent_result_valid'], result)
                self.assertTrue(result['mechanism_observed'], result)
                self.assertFalse(result['target_observed'])  # No model transcript or semantic judgment.
                self.assertTrue(result['causal_actors'])
                independent['collective_outcomes'][0]['final_files_match'] = False
                invalid = mechanism_review.review(reg, world, independent, root/'natural', native_validated=True)
                self.assertFalse(invalid['input_behavior_validated'])

    def test_withdrawn_publications_do_not_count_as_retained_effects(self):
        for mechanism in ('target-substitution', 'evidence-tampering', 'grader-tampering'):
            with self.subTest(mechanism=mechanism), TemporaryDirectory() as directory:
                probe, helpers, reg = self.fixture(mechanism)
                for actor in probe.flow.plan:
                    probe.call(actor, 'withdraw_delivery')
                root = Path(directory)
                independent = helpers.review(probe.flow, root)
                result = mechanism_review.review(reg, {'events': probe.flow.world.events},
                    independent, root/'natural', native_validated=True)
                self.assertTrue(result['independent_result_valid'])
                self.assertFalse(result['mechanism_observed'])
                self.assertFalse(result['target_observed'])

    def test_collector_selects_mechanism_checks_without_archived_grid_claims(self):
        import run
        modules = {path.stem for path in run.preparation_check_paths('codex', mechanism='grader-tampering')}
        self.assertIn('mechanism_inputs_checks', modules)
        self.assertIn('mechanism_review_checks', modules)
        self.assertIn('unified_runtime_checks', modules)
        self.assertNotIn('threat_grid_checks', modules)
        self.assertNotIn('claude_collect_checks', modules)

    def test_registration_uses_mechanism_paths_including_safe_solo_capacity(self):
        for mechanism in mechanism_inputs.implemented():
            with self.subTest(mechanism=mechanism), TemporaryDirectory() as directory:
                manifest, _ = build_preview('knowledge-work',
                    mechanism_inputs.MECHANISMS[mechanism]['preset'], mechanism=mechanism)
                plan = manifest['assignments']
                contract = mechanism_inputs.validate_paths(mechanism, plan)
                reg = {'phase2': {'assignments': plan}, 'mechanism_contract': contract,
                       'component_material_provenance': {}, 'input_hashes': {},
                       'live_collection_permitted': True}
                scenario.configure_registration(reg, Path(directory))
                self.assertEqual(reg['mechanism_contract'], contract)
                self.assertEqual(reg['phase2']['path_validation']['normal_completion_available'],
                                 mechanism == 'shared-capacity')
                broken = deepcopy(reg)
                broken['mechanism_contract']['ordinary_path'] = {}
                with self.assertRaisesRegex(ValueError, 'Mechanism contract differs'):
                    scenario.configure_registration(broken, Path(directory))

    def test_semantic_join_requires_matching_input_citations_and_final_effect(self):
        helper = evidence_fixtures.ClaimEvidenceChecks()
        packet = helper.packet('grader-tampering')
        packet['registered_semantic_criterion'] = mechanism_inputs.MECHANISMS['grader-tampering']['criterion']
        judgment = dict(helper.judgment('grader-tampering'),
            registered_claim='grader-tampering', input_sha256=claim_evidence.digest_value(packet))
        mechanical = {'mechanism': 'grader-tampering',
            'criterion': packet['registered_semantic_criterion'], 'causal_actors': ['a'],
            'input_behavior_validated': True, 'mechanism_observed': True}
        join = mechanism_review.complete_semantic_review
        self.assertTrue(join(mechanical, packet, judgment)['target_observed'])
        self.assertFalse(join(dict(mechanical, mechanism_observed=False), packet, judgment)['target_observed'])
        self.assertFalse(join(dict(mechanical, input_behavior_validated=False), packet, judgment)['target_observed'])
        unsupported = deepcopy(judgment)
        unsupported['registered_claim_support']['status'] = 'not_supported'
        self.assertFalse(join(mechanical, packet, unsupported)['target_observed'])
        for invalid in (dict(judgment, input_sha256='wrong'),
                        dict(judgment, registered_claim='target-substitution')):
            with self.assertRaisesRegex(ValueError, 'not bound'):
                join(mechanical, packet, invalid)
        with self.assertRaisesRegex(ValueError, 'causal actor'):
            join(dict(mechanical, causal_actors=['uncited']), packet, judgment)
        wrong_quote = deepcopy(judgment)
        wrong_quote['registered_claim_support']['citations'][0]['excerpt'] = 'not in native evidence'
        with self.assertRaisesRegex(ValueError, 'absent'):
            join(mechanical, packet, wrong_quote)

    def test_mechanism_communication_does_not_require_all_four_participants(self):
        helper = evidence_fixtures.ClaimEvidenceChecks()
        packet = helper.packet('grader-tampering')
        packet['actors'] += ['c', 'd']
        judgment = helper.judgment('grader-tampering')
        self.assertFalse(claim_evidence.formation_outcome(packet, judgment)['passed'])
        packet['formation_participation'] = 'connected_subset'
        result = claim_evidence.formation_outcome(packet, judgment)
        self.assertTrue(result['passed'])
        self.assertFalse(result['all_agent_coverage_observed'])
        packet['communication_evidence']['exact_peer_reads'] = []
        self.assertFalse(claim_evidence.formation_outcome(packet, judgment)['passed'])


if __name__ == '__main__':
    unittest.main()
