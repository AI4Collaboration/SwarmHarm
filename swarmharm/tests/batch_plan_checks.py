"""Scale plans remain separate conditions and never overwrite attempts."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_matrix as batch
from phase2.mechanism_inputs import CURRENT_CONFIGURATIONS


class BatchPlanChecks(unittest.TestCase):
    def test_scale_plan_has_36_distinct_conditions(self):
        args = SimpleNamespace(populations=[4,8,16], repeats=1,
            scenarios=['engineering-capacity','knowledge-work'],
            mechanisms=list(CURRENT_CONFIGURATIONS), model='gpt-6.1-sol',
            base_url='http://localhost:8000/v1', startup_concurrency=128)
        rows = list(batch.cases(args, 'fixed-source'))
        self.assertEqual(len(rows), 36)
        for row in rows:
            selected = ('data-analysis' if (row['scenario'], row['mechanism']) ==
                        ('knowledge-work', 'task-gaming') else row['scenario'])
            self.assertEqual(row['workload'], selected)
        self.assertEqual(len(set(map(batch.run_id, rows))), 36)
        self.assertTrue(all(r['startup_concurrency'] == r['population'] for r in rows))
        self.assertNotEqual(batch.run_id(rows[0]), batch.run_id({**rows[0], 'model':'different'}))

    def test_existing_unreviewed_capture_stays_incomplete(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'cohort'
            self.assertIsNone(batch.existing_status(root))
            root.mkdir()
            (root/'completion.json').write_text('{"status":"collected"}')
            self.assertEqual(batch.existing_status(root)['status'], 'review_incomplete')
            for name in ('independent-review.json','evidence-manifest.json'):
                (root/name).write_text('{}')
            self.assertEqual(batch.existing_status(root)['status'], 'collected')
            self.assertEqual(batch.existing_status(root, require_judge=True)['status'], 'review_incomplete')
            (root/'mechanism-verdict.json').write_text('{}')
            self.assertEqual(batch.existing_status(root, require_judge=True)['status'], 'collected')

    def test_uncoupled_and_explicit_variant_plans_remain_distinct_from_coupled(self):
        coupled_args = SimpleNamespace(populations=[4,8], repeats=1,
            scenarios=['engineering-capacity','knowledge-work'],
            mechanisms=list(CURRENT_CONFIGURATIONS), model='gpt-6.1-sol',
            base_url='http://localhost:8000/v1', startup_concurrency=16,
            coupling='coupled', input_variant=None)
        uncoupled_args = SimpleNamespace(**{**vars(coupled_args), 'coupling':'uncoupled'})
        coupled_rows = list(batch.cases(coupled_args, 'fixed-source'))
        uncoupled_rows = list(batch.cases(uncoupled_args, 'fixed-source'))
        self.assertEqual(len(uncoupled_rows), 24)
        self.assertTrue(all('input_variant' not in r for r in coupled_rows))
        self.assertTrue(all(r.get('input_variant', '').endswith('-uncoupled-v1') for r in uncoupled_rows))
        self.assertFalse(set(map(batch.run_id, coupled_rows)) & set(map(batch.run_id, uncoupled_rows)))
        targeted_args = SimpleNamespace(populations=[4,8,16], repeats=1,
            scenarios=['knowledge-work'], mechanisms=['grader-tampering'],
            model='gpt-6.1-sol', base_url='http://localhost:8000/v1', startup_concurrency=16,
            coupling='coupled', input_variant='knowledge-grader-tampering-reconciled-schema-v1')
        targeted_rows = list(batch.cases(targeted_args, 'fixed-source'))
        self.assertEqual(len(targeted_rows), 3)
        self.assertTrue(all(r['input_variant'] == 'knowledge-grader-tampering-reconciled-schema-v1' for r in targeted_rows))
        ext_args = SimpleNamespace(**{**vars(coupled_args), 'populations':[4], 'variant_suite':'extended'})
        ext_rows = list(batch.cases(ext_args, 'fixed-source'))
        self.assertEqual(len(ext_rows), len(batch.mechanism_inputs.EXTENDED_SUITE_VARIANTS))
        all_rows = list(batch.cases(SimpleNamespace(**{**vars(ext_args), 'variant_suite':'all'}), 'fixed-source'))
        self.assertEqual(len(all_rows), 12 + len(ext_rows))

    def test_checks_reused_only_when_required_modules_are_covered(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'registration-seal.json').write_text('{}')
            (root/'registration.json').write_text(json.dumps({'code_hashes':{
                str(path.relative_to(batch.run.REPO)): batch.run.sha(path)
                for path in batch.run.code_paths()}}))
            (root/'controls.json').write_text(json.dumps(
                {'passed':True, 'check_modules':['tests/first_checks.py']}))
            row = {'mechanism':'task-gaming', 'scenario':'knowledge-work', 'harness':'codex'}
            with patch.object(batch.run, 'preparation_check_paths', return_value=[
                    batch.run.HERE/'tests/first_checks.py']):
                self.assertEqual(batch.reusable_controls([{'output':str(root)}], row),
                                 ['--controls-from', str(root)])
            with patch.object(batch.run, 'preparation_check_paths', return_value=[
                    batch.run.HERE/'tests/another_checks.py']):
                self.assertEqual(batch.reusable_controls([{'output':str(root)}], row), [])

    def test_old_controls_are_skipped_before_selecting_current_source(self):
        with TemporaryDirectory() as directory:
            source = batch.run.HERE/'run_matrix.py'
            expected = {str(source.relative_to(batch.run.REPO)): batch.run.sha(source)}
            records = []
            for name, hashes in [('old', {'old.py':'old-hash'}), ('current', expected)]:
                root = Path(directory)/name
                root.mkdir()
                (root/'registration-seal.json').write_text('{}')
                (root/'registration.json').write_text(json.dumps({'code_hashes':hashes}))
                (root/'controls.json').write_text(json.dumps(
                    {'passed':True, 'check_modules':['tests/first_checks.py']}))
                records.append({'output':str(root), 'source_sha256':'same-batch-label'})
            row = {'mechanism':'task-gaming', 'scenario':'knowledge-work', 'harness':'codex'}
            with patch.object(batch.run, 'code_paths', return_value=[source]), \
                    patch.object(batch.run, 'preparation_check_paths', return_value=[
                        batch.run.HERE/'tests/first_checks.py']):
                self.assertEqual(batch.reusable_controls(records[:1], row), [])
                self.assertEqual(batch.reusable_controls(records, row),
                                 ['--controls-from', records[1]['output']])

    def test_missing_archive_never_restarts_collection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'cohort'
            root.with_name('cohort.archive.json').write_text(json.dumps(
                {'archive': str(root)+'.tar.gz', 'sha256':'fixture'}))
            self.assertEqual(batch.existing_status(root)['status'], 'archive_missing')

    def test_batch_lock_rejects_concurrent_runner_on_same_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'batch'
            with batch.batch_lock(root):
                with self.assertRaises(RuntimeError):
                    with batch.batch_lock(root):
                        pass

    def test_review_incomplete_resumes_only_missing_judge_step(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'out'
            key = Path(directory)/'key'; key.write_text('secret\n')
            args = SimpleNamespace(
                populations=[4], repeats=1, scenarios=['knowledge-work'],
                mechanisms=['task-gaming'], model='openai/gpt-6.1-sol',
                served_model='openai/gpt-6.1-sol', api_protocol='chat-completions',
                base_url='http://localhost:8000/v1', startup_concurrency=4,
                coupling='coupled', input_variant=None, judge=True,
                judge_model='openai/gpt-6.1-sol', max_attempts=2,
                retry_backoff_seconds=0.0, key_file=key, out=root)
            rows = list(batch.cases(args, 'fixed-source'))
            name = batch.run_id(rows[0])
            cohort = root/'openai-gpt-6.1-sol'/'n4'/name
            cohort.mkdir(parents=True)
            (cohort/'completion.json').write_text('{"status":"collected"}')
            (cohort/'atif-validation.json').write_text('{}')
            (cohort/'independent-review.json').write_text('{}')
            (cohort/'evidence-manifest.json').write_text('{}')
            called = []

            def fake_run_process(argv, **kwargs):
                called.append(argv)
                if any('judge_unified_transcript.py' in str(x) for x in argv):
                    (cohort/'mechanism-verdict.json').write_text('{"target_observed":true}')
                return 0, None

            with patch.object(batch, 'run_process', side_effect=fake_run_process), \
                 patch.object(batch.subprocess, 'check_output', return_value=''):
                rc = batch.execute_rows(args, rows, root, SimpleNamespace(error=self.fail))
            self.assertEqual(rc, 0)
            self.assertEqual(len(called), 1)
            self.assertIn('judge_unified_transcript.py', ' '.join(map(str, called[0])))
            index = json.loads((root/'index.json').read_text())
            self.assertEqual(index['runs'][0]['status'], 'collected')
            self.assertTrue(index['runs'][0]['resumed_review'])

    def test_transient_cohort_failure_preserves_attempt_one_and_retries_attempt_two(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'out'
            fake_regs = Path(directory)/'regs'; fake_regs.mkdir()
            key = Path(directory)/'key'; key.write_text('secret\n')
            args = SimpleNamespace(
                populations=[4], repeats=1, scenarios=['knowledge-work'],
                mechanisms=['task-gaming'], model='openai/gpt-6.1-sol',
                served_model='openai/gpt-6.1-sol', api_protocol='chat-completions',
                base_url='http://localhost:8000/v1', startup_concurrency=4,
                coupling='coupled', input_variant=None, judge=False,
                judge_model=None, max_attempts=2, retry_backoff_seconds=0.0,
                key_file=key, out=root)
            rows = list(batch.cases(args, 'fixed-source'))

            def fake_run_process(argv, **kwargs):
                cmd = ' '.join(map(str, argv))
                out_idx = argv.index('--output') + 1 if '--output' in argv else None
                out_dir = Path(argv[out_idx]) if out_idx else None
                if '--phase prepare' in cmd:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    return 0, None
                if '--phase collect' in cmd:
                    if not str(out_dir).endswith('-attempt-002'):
                        (out_dir/'completion.json').write_text('{"status":"collector_error"}')
                        return 1, None
                    (out_dir/'completion.json').write_text('{"status":"collected"}')
                    (out_dir/'evidence-manifest.json').write_text('{}')
                    return 0, None
                if 'export_atif.py' in cmd:
                    Path(argv[-1], 'atif-validation.json').write_text('{}')
                if 'review.py' in cmd:
                    (out_dir/'independent-review.json').write_text('{}')
                return 0, None

            with patch.object(batch, 'run_process', side_effect=fake_run_process), \
                 patch.object(batch, 'reap_dead_owner_resources'), \
                 patch.object(batch.run, 'REGISTRATIONS', fake_regs), \
                 patch.object(batch.subprocess, 'check_output', return_value=''):
                rc = batch.execute_rows(args, rows, root, SimpleNamespace(error=self.fail))
            self.assertEqual(rc, 0)
            index = json.loads((root/'index.json').read_text())
            rec = index['runs'][0]
            self.assertEqual(rec['status'], 'collected')
            self.assertTrue(rec['output'].endswith('-attempt-002'))
            self.assertEqual(len(rec['prior_attempts']), 1)
            self.assertEqual(rec['prior_attempts'][0]['status'], 'collector_error')
            self.assertTrue(Path(rec['prior_attempts'][0]['output']).is_dir())
            self.assertFalse(batch.is_retryable_attempt({'status': 'rollout_limit'}, Path(directory)/'missing.log'))

    def test_execute_rows_supplies_fallback_git_identity_when_unconfigured(self):
        import os
        with TemporaryDirectory() as directory:
            root = Path(directory)/'out'
            fake_regs = Path(directory)/'regs'; fake_regs.mkdir()
            empty_home = Path(directory)/'empty-home'; empty_home.mkdir()
            key = Path(directory)/'key'; key.write_text('secret\n')
            args = SimpleNamespace(
                populations=[4], repeats=1, scenarios=['knowledge-work'],
                mechanisms=['task-gaming'], model='openai/gpt-6.1-sol',
                served_model='openai/gpt-6.1-sol', api_protocol='chat-completions',
                base_url='http://localhost:8000/v1', startup_concurrency=4,
                coupling='coupled', input_variant=None, judge=False,
                judge_model=None, max_attempts=1, retry_backoff_seconds=0.0,
                key_file=key, out=root)
            rows = list(batch.cases(args, 'fixed-source'))
            seen_envs = []

            def fake_run_process(argv, **kwargs):
                seen_envs.append(kwargs.get('env', {}))
                cmd = ' '.join(map(str, argv))
                out_idx = argv.index('--output') + 1 if '--output' in argv else None
                out_dir = Path(argv[out_idx]) if out_idx else None
                if '--phase prepare' in cmd:
                    out_dir.mkdir(parents=True, exist_ok=True)
                elif '--phase collect' in cmd:
                    (out_dir/'completion.json').write_text('{"status":"collected"}')
                    (out_dir/'evidence-manifest.json').write_text('{}')
                elif 'export_atif.py' in cmd:
                    Path(argv[-1], 'atif-validation.json').write_text('{}')
                elif 'review.py' in cmd:
                    (out_dir/'independent-review.json').write_text('{}')
                return 0, None

            clean_env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
            clean_env.update(HOME=str(empty_home), GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
            with patch.dict(os.environ, clean_env, clear=True), \
                 patch.object(batch, 'run_process', side_effect=fake_run_process), \
                 patch.object(batch, 'reap_dead_owner_resources'), \
                 patch.object(batch.run, 'REGISTRATIONS', fake_regs), \
                 patch.object(batch.subprocess, 'check_output', return_value=''):
                rc = batch.execute_rows(args, rows, root, SimpleNamespace(error=self.fail))
            self.assertEqual(rc, 0)
            self.assertTrue(seen_envs)
            for env in seen_envs:
                self.assertEqual(env.get('GIT_AUTHOR_NAME'), 'SwarmHarm Runner')
                self.assertEqual(env.get('GIT_COMMITTER_NAME'), 'SwarmHarm Runner')

    def test_swarmharm_rejects_n64(self):
        args = SimpleNamespace(populations=[4, 64], repeats=1, scenarios=['knowledge-work'],
            mechanisms=['task-gaming'], model='gpt-6.1-sol',
            base_url='http://localhost:8000/v1', startup_concurrency=16)
        with self.assertRaisesRegex(ValueError, 'N=64 is not part of this study'):
            list(batch.cases(args, 'fixed-source'))

    def test_reasoning_effort_and_n32_default_timeout_scaling(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'out'
            fake_regs = Path(directory)/'regs'; fake_regs.mkdir()
            key = Path(directory)/'key'; key.write_text('secret\n')
            args = SimpleNamespace(
                populations=[4, 32], repeats=1, scenarios=['knowledge-work'],
                mechanisms=['task-gaming'], model='anthropic/claude-opus-5.5',
                served_model='azure/anthropic/claude-opus-5-5', api_protocol='chat-completions',
                base_url='http://localhost:8000/v1', startup_concurrency=16,
                reasoning_effort='medium', max_actor_seconds=None,
                coupling='coupled', input_variant=None, judge=False,
                judge_model=None, max_attempts=1, retry_backoff_seconds=0.0,
                key_file=key, out=root)
            rows = list(batch.cases(args, 'fixed-source'))
            self.assertTrue(all(r['reasoning_effort'] == 'medium' for r in rows))
            prep_cmds = []

            def fake_run_process(argv, **kwargs):
                cmd = ' '.join(map(str, argv))
                out_idx = argv.index('--output') + 1 if '--output' in argv else None
                out_dir = Path(argv[out_idx]) if out_idx else None
                if '--phase prepare' in cmd:
                    prep_cmds.append(argv)
                    out_dir.mkdir(parents=True, exist_ok=True)
                elif '--phase collect' in cmd:
                    (out_dir/'completion.json').write_text('{"status":"collected"}')
                    (out_dir/'evidence-manifest.json').write_text('{}')
                elif 'export_atif.py' in cmd:
                    Path(argv[-1], 'atif-validation.json').write_text('{}')
                elif 'review.py' in cmd:
                    (out_dir/'independent-review.json').write_text('{}')
                return 0, None

            with patch.object(batch, 'run_process', side_effect=fake_run_process), \
                 patch.object(batch, 'reap_dead_owner_resources'), \
                 patch.object(batch.run, 'REGISTRATIONS', fake_regs), \
                 patch.object(batch.subprocess, 'check_output', return_value=''):
                rc = batch.execute_rows(args, rows, root, SimpleNamespace(error=self.fail))
            self.assertEqual(rc, 0)
            self.assertEqual(len(prep_cmds), 2)
            for cmd in prep_cmds:
                self.assertEqual(cmd[cmd.index('--reasoning-effort') + 1], 'medium')
            self.assertNotIn('--max-actor-seconds', prep_cmds[0])
            self.assertEqual(prep_cmds[1][prep_cmds[1].index('--max-actor-seconds') + 1], '4500')

    def test_single_agent_n1_plan_generates_12_distinct_conditions(self):
        args = SimpleNamespace(populations=[1], repeats=1,
            scenarios=['engineering-capacity', 'knowledge-work'],
            mechanisms=list(CURRENT_CONFIGURATIONS), model='gpt-6.1-sol',
            base_url='http://localhost:8000/v1', startup_concurrency=16,
            coupling='coupled', input_variant=None)
        rows = list(batch.cases(args, 'fixed-source'))
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(r['population'] == 1 and r['startup_concurrency'] == 1 for r in rows))
        self.assertEqual(len(set(map(batch.run_id, rows))), 12)


if __name__ == '__main__':
    unittest.main()
