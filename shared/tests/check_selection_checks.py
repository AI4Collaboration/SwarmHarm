"""Regression coverage for lightweight check selection; no runtime or model needed."""
from pathlib import Path
import os
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
ENTRY = runpy.run_path(str(ROOT / 'scripts/check-ci'))
select = ENTRY['select_checks']
changed = ENTRY['changed_files']


class CheckSelectionChecks(unittest.TestCase):
    def test_portable_handoff_does_not_select_historical_suite(self):
        plan = select(['rollouts/run_matrix.py', 'rollouts/tests/__init__.py',
                       'scripts/archive-trajectories', 'swarmharm/run_matrix.py'])
        self.assertEqual(plan['tests'], ['tests.api_handoff_checks',
            'tests.batch_plan_checks', 'tests.portable_runtime_checks', 'tests.trajectory_archive_checks'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_reporting_collectors_share_the_docker_concurrency_limit(self):
        for stem in ('build_record_collector', 'codex_notice_collector', 'continuous_collect',
                     'review', 'continuous_reporting', 'delivery_receipt'):
            with self.subTest(stem=stem):
                self.assertTrue(ENTRY['uses_docker'](stem))
                root = 'swarmharm'
                plan = select([f'{root}/tests/{stem}_checks.py'])
                self.assertTrue(plan['docker'])
        self.assertFalse(ENTRY['uses_docker']('domain_runtime'))
        for path in ('swarmharm/tests/local_source_checks.py',
                     'swarmharm/tests/unified_delivery_checks.py'):
            with self.subTest(path=path):
                self.assertIn('codex', select([path])['harnesses'])

    def test_reporting_observation_changes_select_minimalist_core_contracts(self):
        for name in ('unified_delivery', 'world_config'):
            plan = select([f'swarmharm/phase2/{name}.py'])
            self.assertEqual(plan['tests'], [
                'tests.claim_evidence_checks',
                'tests.mechanism_inputs_checks',
                'tests.mechanism_review_checks',
                'tests.unified_input_contract_checks',
            ])
            self.assertFalse(plan['docker'])
            self.assertEqual(plan['harnesses'], [])

    def test_reporting_entry_checks_remain_fast_and_offline(self):
        plan = select(['swarmharm/run.py'])
        self.assertEqual(plan['tests'], [
            'tests.batch_plan_checks',
            'tests.domain_runtime_checks',
            'tests.shutdown_checks',
            'tests.unified_notification_checks',
        ])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_adapter_edits_install_only_their_own_harness_while_native_harness_installs_all(self):
        for path, expected in (
                ('shared/codex_session.py', ['codex']),
                ('shared/claude_agent.py', ['claude']),
                ('shared/pi_agent.py', ['pi']),
                ('swarmharm/tests/native_harness_checks.py', ['claude', 'codex', 'pi'])):
            with self.subTest(path=path):
                plan = select([path])
                self.assertEqual(plan['harnesses'], expected)
                self.assertTrue(plan['docker'])

    def test_documentation_and_pause_notes_need_no_runtime(self):
        plan = select(['README.md', 'AGENTS.md', 'swarmharm/README.md',
                       'swarmharm/phase1/README.md', 'swarmharm/phase2/README.md',
                       'swarmharm/registrations/README.md',
                       'swarmform/docs/formation-readiness.json'])
        self.assertEqual(plan['checks'], ['syntax', 'inventory'])
        self.assertEqual(plan['tests'], [])
        self.assertFalse(plan['dependencies'])
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_worker_markdown_is_not_treated_as_operator_documentation(self):
        plan = select(['swarmharm/instruction.md'])
        self.assertTrue(plan['tests'])

    def test_shared_runtime_is_minimalist_and_full_keeps_complete_coverage(self):
        minimal = select(['shared/workstation.py', 'shared/launch_capacity.py', 'shared/export_atif.py'])
        self.assertFalse(minimal['docker'])
        self.assertEqual(minimal['harnesses'], [])
        self.assertIn('tests.host_capacity_checks', minimal['tests'])
        self.assertIn('tests.claim_evidence_checks', minimal['tests'])
        complete = select([], full=True)
        self.assertTrue(complete['docker'])
        self.assertEqual(complete['harnesses'], ['claude', 'codex', 'pi'])
        self.assertIn('tests.review_checks', complete['tests'])
        self.assertIn('tests.api_collect_checks', complete['tests'])
        self.assertIn('tests.unified_delivery_checks', complete['tests'])

    def test_overlapping_selections_execute_each_suite_once(self):
        plan = select(['scripts/check-ci', 'shared/tests/check_selection_checks.py',
                       'shared/workstation.py'], full=True)
        self.assertEqual(len(plan['tests']), len(set(plan['tests'])))
        self.assertEqual(plan['checks'].count('format'), 1)
        self.assertNotIn('tests.format_checks', plan['tests'])
        self.assertEqual(plan['checks'].count('catalog'), 1)
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
