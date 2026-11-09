"""Regression coverage for lightweight check selection; no runtime or model needed."""
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
ENTRY = runpy.run_path(str(ROOT / 'scripts/check-ci'))
select = ENTRY['select_checks']
changed = ENTRY['changed_files']


class CheckSelectionChecks(unittest.TestCase):
    def test_documentation_and_pause_notes_need_no_runtime(self):
        plan = select(['README.md', 'AGENTS.md', 'docs/research/swarmform-input-development.json'])
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
        self.assertFalse(plan['docker'])
        self.assertEqual(plan['harnesses'], [])

    def test_worker_markdown_is_not_treated_as_operator_documentation(self):
        plan = select(['experiments/swarmharm-v1/instruction.md'])
        self.assertIn('wording', plan['checks'])
        self.assertTrue(plan['tests'])

    def test_shared_workstation_and_full_checks_keep_runtime_coverage(self):
        for plan in (select(['experiments/runtime/workstation.py']), select([], full=True)):
            self.assertTrue(plan['docker'])
            self.assertEqual(plan['harnesses'], ['claude', 'codex', 'pi'])
            self.assertIn('tests.swarmform_collection_checks', plan['tests'])
            self.assertIn('tests.review_checks', plan['tests'])

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
        with tempfile.TemporaryDirectory() as folder:
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
