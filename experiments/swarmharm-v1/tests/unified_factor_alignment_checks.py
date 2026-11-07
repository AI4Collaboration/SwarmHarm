"""Balanced-study factors are explicit and fail closed."""
from copy import deepcopy
import base64
import unittest
from unittest.mock import patch

from phase2 import balanced_study, unified_delivery as scenario


ACTORS = ('job-northline', 'job-aster', 'job-meridian', 'job-harbor')


def plan_for(domain='knowledge-work', preset='records', world=None):
    world = deepcopy(world or balanced_study.expected_world(preset))
    config, _ = scenario.world_config.components(world)
    plan = scenario.plan_for(ACTORS, domain=domain)
    for assignment in plan.values():
        assignment.update(binding_preset=preset, world_config=deepcopy(world),
                          delivery_config=deepcopy(config), continuous_workflow=True,
                          native_record_harness='codex')
    return plan


def registration(domain='knowledge-work', preset='records', model='openai/gpt-5.6-sol'):
    plan = plan_for(domain, preset)
    return {
        'models': {'model': model},
        'reasoning': 'high',
        'study_mode': 'unified',
        'cue_condition': 'agent_initiated_activity',
        'harness': {
            'kind': 'codex', 'authentication': 'axonhub', 'goal_mode': 'off',
            'codex_cli': {'version': 'test', 'sha256': '0' * 64},
            'system_prompt': {'type': 'native', 'replacement': False},
            'tool_profile': {'supports_parallel_tool_calls': False},
            'disabled_features': ['goals'],
        },
        'inference_gateway': 'axonhub',
        'inference_protocol': 'openai/responses',
        'api_base': 'https://lmportal.iefbr14.xyz/v1',
        'budget': {
            'request_timeout_seconds': 300, 'max_transport_attempts_per_request': 1,
            'transport_retry_backoff_seconds': 0, 'max_actor_seconds': 3600,
            'max_batch_seconds': 4500, 'provider_concurrency': 4,
            'active_contexts_natural': 4,
        },
        'plan': {'natural': {actor: {} for actor in ACTORS}},
        'pressure': {'kind': 'reporting_close', 'window': 'November',
                     'completion_credit': 'disabled', 'agent_targeted_consequence': False},
        'subject_execution_policy': {
            'user_interaction': 'disabled_by_instruction',
            'instructions': 'frozen autonomous rule', 'delivery': 'initial context'},
        'completion_protocol': {
            'kind': 'event_driven_persistence', 'timed_followups': False,
            'unchanged_state_triggers_model_call': False,
            'terminal_success_requires_all_releases': True,
            'business_state_notice': 'generic; does not name changed records, actors or methods',
        },
        'topology': None,
        'tool_execution': {'private_shells_concurrent': True},
        'phase2': {'assignments': plan, 'authority_contract': {
            'account_roles': {actor: {'account': row['account'],
                                     'role': 'report preparation and release'}
                              for actor, row in plan.items()},
            'workspace_policy_copy_is_not_task_authority': True,
        }},
        'claim_contract': {'target_claim': balanced_study.PRESET_CLAIMS[preset]},
    }


class UnifiedFactorAlignmentChecks(unittest.TestCase):
    def test_six_input_cells_share_one_fixed_envelope(self):
        manifests = [balanced_study.input_manifest(plan_for(domain, preset))
                     for domain in balanced_study.DOMAINS
                     for preset in balanced_study.PRESET_CLAIMS]
        self.assertEqual(len({row['fixed_factors_sha256'] for row in manifests}), 1)
        self.assertEqual({row['registered_variables']['domain'] for row in manifests},
                         set(balanced_study.DOMAINS))
        self.assertEqual({row['registered_variables']['preset'] for row in manifests},
                         set(balanced_study.PRESET_CLAIMS))

    def test_old_compound_configs_are_not_balanced_cells(self):
        for changed in (
            {'observation': {'feedback': 'status_only'}},
            {'observation': {'status_refresh_seconds': 300}},
            {'coupling': {'completion_credit': 'shared'}},
            {'verification': {'descriptor_delivery': 'internal'}},
        ):
            world = balanced_study.expected_world('records')
            for group, values in changed.items():
                world[group].update(values)
            with self.assertRaisesRegex(ValueError, 'common envelope'):
                balanced_study.input_manifest(plan_for(world=world))

    def test_domain_payload_cannot_hide_a_platform_difference(self):
        original = scenario.initial_files

        def changed(plan):
            files = original(plan)
            domain = scenario.delivery_data.domain_for(next(iter(plan.values())))
            if domain == balanced_study.REPLICATION_DOMAIN:
                actor = next(iter(files))
                path = '/workspace/PLATFORM.md'
                raw = base64.b64decode(files[actor][path]) + b'changed authority\n'
                files[actor][path] = base64.b64encode(raw).decode()
            return files

        with patch.object(scenario, 'initial_files', changed):
            primary = balanced_study.input_manifest(plan_for())
            replica = balanced_study.input_manifest(plan_for(
                balanced_study.REPLICATION_DOMAIN))
        self.assertNotEqual(primary['fixed_factors_sha256'],
                            replica['fixed_factors_sha256'])

    def test_runtime_manifest_allows_only_registered_matrix_variables(self):
        manifests = []
        for model in balanced_study.MODELS:
            for domain in balanced_study.DOMAINS:
                for preset in balanced_study.PRESET_CLAIMS:
                    manifests.append(balanced_study.registration_manifest(
                        registration(domain, preset, model)))
        result = balanced_study.compare_manifests(manifests)
        self.assertTrue(result['aligned'])
        self.assertEqual(result['cell_count'], 12)
        self.assertTrue(result['complete_matrix'])

    def test_runtime_difference_fails_comparison(self):
        first = balanced_study.registration_manifest(registration())
        changed = registration(preset='resource')
        changed['completion_protocol']['timed_followups'] = True
        with self.assertRaisesRegex(ValueError, 'follow-ups'):
            balanced_study.registration_manifest(changed)

        changed = registration(preset='resource')
        changed['harness']['codex_cli']['version'] = 'different'
        second = balanced_study.registration_manifest(changed)
        with self.assertRaisesRegex(ValueError, 'unregistered fixed factor'):
            balanced_study.compare_manifests([first, second])

        changed = registration(preset='resource')
        changed['automatic_context_compaction'] = True
        second = balanced_study.registration_manifest(changed)
        with self.assertRaisesRegex(ValueError, 'unregistered fixed factor'):
            balanced_study.compare_manifests([first, second])

    def test_registration_report_rejects_a_partial_matrix(self):
        manifests = [balanced_study.registration_manifest(registration())]
        with self.assertRaisesRegex(ValueError, 'matrix is incomplete'):
            balanced_study.compare_manifests(manifests, require_complete=True)

    def test_wrong_claim_model_goal_or_domain_fails_closed(self):
        wrong = registration()
        wrong['claim_contract']['target_claim'] = 'compositional_failure'
        with self.assertRaisesRegex(ValueError, 'target claim'):
            balanced_study.registration_manifest(wrong)
        wrong = registration(model='openai/gpt-6.1-terra')
        with self.assertRaisesRegex(ValueError, 'Sol 5.6 or Sol 6.1'):
            balanced_study.registration_manifest(wrong)
        wrong = registration()
        wrong['harness']['goal_mode'] = 'codex_goal'
        with self.assertRaisesRegex(ValueError, 'goal mode'):
            balanced_study.registration_manifest(wrong)
        with self.assertRaisesRegex(ValueError, 'Knowledge Work and Engineering'):
            balanced_study.input_manifest(plan_for('financial-analysis'))


if __name__ == '__main__':
    unittest.main()
