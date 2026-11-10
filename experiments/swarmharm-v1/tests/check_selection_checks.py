"""Regression coverage for lightweight check selection; no runtime or model needed."""
from pathlib import Path
import os
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
ENTRY = runpy.run_path(str(ROOT / 'scripts/check-ci'))
select = ENTRY['select_checks']
changed = ENTRY['changed_files']


class CheckSelectionChecks(unittest.TestCase):
    def test_structure_operator_observations_need_no_native_model_runtime(self):
        for name in ('communication_inventory','artifact_use_timeline','exact_source_use','shared_content_inventory','source_pool_review','common_problem_review'):
            plan=select([f'experiments/structure/{name}.py'])
            self.assertEqual(plan['tests'],['tests.structure_observations_checks'])
            self.assertFalse(plan['docker'])
            self.assertEqual(plan['harnesses'],[])

    def test_structure_runtime_has_its_native_and_temporal_checks(self):
        plan=select(['scripts/run_swarmform_structure.py',
                     'experiments/swarmharm-v1/swarmform/structure_collection.py'])
        self.assertEqual(plan['tests'],['tests.publication_updates_checks', 'tests.structure_native_checks','tests.structure_timeline_checks',
                                       'tests.swarmform_structure_checks'])
        self.assertTrue(plan['docker'])
        self.assertEqual(plan['harnesses'],['codex'])

    def test_documentation_and_pause_notes_need_no_runtime(self):
        plan = select(['README.md', 'AGENTS.md', 'docs/research/swarmform-input-archives.json'])
        self.assertEqual(plan['checks'], ['syntax', 'inventory'])
        self.assertEqual(plan['tests'], [])
        self.assertFalse(plan['dependencies'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_operator_edits_do_not_replay_history_or_build_inputs(self):
        plan = select(['scripts/check_swarmform_ipc_inputs.py', 'scripts/swarmform_service_witness_codecs.py'])
        self.assertEqual(plan['tests'], ['tests.swarmform_input_runner_checks'])
        self.assertNotIn('catalog', plan['checks'])
        self.assertNotIn('wording', plan['checks'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_input_changes_keep_relevant_contract_and_wording_checks(self):
        plan = select(['experiments/swarmharm-v1/swarmform/inputs.py'])
        self.assertIn('catalog', plan['checks'])
        self.assertIn('wording', plan['checks'])
        self.assertIn('tests.swarmform_registration_checks', plan['tests'])
        self.assertTrue(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_worker_markdown_is_not_treated_as_operator_documentation(self):
        plan = select(['experiments/swarmharm-v1/instruction.md'])
        self.assertIn('wording', plan['checks'])
        self.assertTrue(plan['tests'])

    def test_job_service_edits_check_its_api_and_source_binding(self):
        plan = select(['experiments/swarmharm-v1/swarmform/job_service.py'])
        self.assertEqual(plan['tests'], ['tests.swarmform_job_service_checks',
                                         'tests.swarmform_registration_checks'])
        self.assertIn('wording', plan['checks'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_endpoint_service_edits_keep_delivery_input_and_registration_checks(self):
        plan = select(['experiments/swarmharm-v1/swarmform/endpoint_service.py'])
        self.assertEqual(plan['tests'], ['tests.swarmform_delivery_state_checks',
            'tests.swarmform_domain_checks', 'tests.swarmform_package_checks',
            'tests.swarmform_registration_checks'])
        for check in ('inputs', 'catalog', 'wording'):
            self.assertIn(check, plan['checks'])
        self.assertTrue(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_archive_policy_binding_keeps_registration_without_unrelated_harnesses(self):
        for stem in ('archive_deployment',):
            plan=select([f'experiments/swarmharm-v1/swarmform/{stem}.py'])
            self.assertEqual(plan['tests'],['tests.swarmform_archive_outcome_checks',
                'tests.swarmform_archive_policy_checks','tests.swarmform_collection_checks',
                'tests.swarmform_input_runner_checks','tests.swarmform_registration_checks'])
            for check in ('inputs','catalog','wording'):
                self.assertIn(check,plan['checks'])
            self.assertFalse(plan['docker'])
            self.assertEqual(plan['harnesses'],[])

    def test_job_policy_binding_skips_unrelated_workload_and_container_checks(self):
        plan=select(['experiments/swarmharm-v1/swarmform/job_deployment.py',
                     'experiments/swarmharm-v1/swarmform/deployments.py'])
        self.assertEqual(plan['tests'],['tests.swarmform_collection_checks',
            'tests.swarmform_input_runner_checks','tests.swarmform_job_service_checks',
            'tests.swarmform_registration_checks','tests.swarmform_service_cleanup_checks'])
        for check in ('inputs','catalog','wording'):
            self.assertIn(check,plan['checks'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'],[])

    def test_archive_service_edits_do_not_select_unrelated_harnesses(self):
        plan = select(['experiments/swarmharm-v1/swarmform/base_archive.py',
                       'experiments/swarmharm-v1/swarmform/profile_archive.py'])
        self.assertEqual(plan['tests'], ['tests.swarmform_archive_outcome_checks',
                                         'tests.swarmform_archive_policy_checks'])
        self.assertIn('wording', plan['checks'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_ipc_policy_and_binding_select_narrow_suites(self):
        plan=select(['experiments/swarmharm-v1/swarmform/ipc_policy.py',
                     'experiments/swarmharm-v1/swarmform/ipc_deployment.py'])
        self.assertEqual(plan['tests'],['tests.swarmform_collection_checks',
            'tests.swarmform_input_runner_checks','tests.swarmform_registration_checks'])
        for check in ('inputs','catalog','wording'):
            self.assertIn(check,plan['checks'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'],[])

    def test_ipc_business_helpers_check_inputs_without_unrelated_docker_suites(self):
        for helper in ('ipc_status', 'ipc_queue', 'ipc_processor'):
            with self.subTest(helper=helper):
                plan = select([f'experiments/swarmharm-v1/swarmform/{helper}.py'])
                self.assertEqual(plan['tests'], ['tests.swarmform_input_runner_checks',
                                                 'tests.swarmform_registration_checks'])
                self.assertIn('wording', plan['checks'])
                self.assertFalse(plan['docker'])
                self.assertEqual(plan['harnesses'], [])

    def test_service_client_edits_keep_http_and_input_checks_without_docker(self):
        for client in ('archive_client', 'job_client', 'endpoint_client', 'endpoint_inventory', 'endpoint_release_notes'):
            plan = select([f'experiments/swarmharm-v1/swarmform/{client}.py'])
            self.assertEqual(plan['tests'], ['tests.swarmform_input_runner_checks',
                'tests.swarmform_job_service_checks', 'tests.swarmform_registration_checks'])
            self.assertIn('wording', plan['checks'])
            self.assertFalse(plan['docker'])
            self.assertEqual(plan['harnesses'], [])

    def test_shared_workstation_and_full_checks_keep_runtime_coverage(self):
        for plan in (select(['experiments/runtime/workstation.py']), select([], full=True)):
            self.assertTrue(plan['docker'])
            self.assertEqual(plan['harnesses'], ['claude', 'codex', 'pi'])
            self.assertIn('tests.swarmform_collection_checks', plan['tests'])
            self.assertIn('tests.review_checks', plan['tests'])

    def test_delivery_archive_edits_keep_business_checks_without_native_sessions(self):
        for helper in ('delivery_archive', 'delivered_outcome'):
            plan = select([f'experiments/swarmharm-v1/swarmform/{helper}.py'])
            self.assertEqual(plan['tests'], ['tests.swarmform_archive_outcome_checks',
                'tests.swarmform_delivery_state_checks', 'tests.swarmform_domain_checks',
                'tests.swarmform_package_checks'])
            self.assertTrue(plan['docker'])
            self.assertEqual(plan['harnesses'], [])

    def test_overlapping_selections_execute_each_suite_once(self):
        plan = select(['scripts/check-ci', 'experiments/swarmharm-v1/tests/check_selection_checks.py',
                       'experiments/runtime/workstation.py'], full=True)
        self.assertEqual(len(plan['tests']), len(set(plan['tests'])))
        self.assertEqual(plan['checks'].count('format'), 1)
        self.assertNotIn('tests.format_checks', plan['tests'])
        self.assertEqual(plan['checks'].count('inputs'), 1)
        self.assertEqual(plan['tests'].count('tests.check_selection_checks'), 1)

    def test_check_infrastructure_can_test_itself_without_installation(self):
        plan = select(list(ENTRY['SELF']))
        self.assertEqual(plan['tests'], ['tests.check_selection_checks'])
        self.assertFalse(plan['dependencies'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_commit_range_deletions_local_edits_and_first_push(self):
        # A pre-push hook exports GIT_DIR; a fixture must never inherit the real repo.
        fixture_env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        with patch.dict(os.environ, fixture_env, clear=True), tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, text=True).strip()

            git('init', '-q')
            git('config', 'user.name', 'Check fixture')
            git('config', 'user.email', 'fixture@example.test')
            (root / 'old.md').write_text('initial\n')
            git('add', '.')
            git('commit', '-qm', 'initial')
            base = git('rev-parse', 'HEAD')
            (root / 'runner.py').write_text('a = 1\n')
            git('add', '.')
            git('commit', '-qm', 'code change')
            git('rm', 'old.md')
            git('commit', '-qm', 'remove doc')
            (root / 'local.md').write_text('untracked\n')
            self.assertEqual(changed(base, root=root, working=False), ['old.md', 'runner.py'])
            self.assertEqual(changed(base, root=root), ['local.md', 'old.md', 'runner.py'])
            self.assertEqual(changed('0' * 40, root=root, working=False), ['runner.py'])
            self.assertEqual(changed(root=root, working=False), ['runner.py'])
            self.assertEqual(changed('HEAD', root=root, working=False), [])
