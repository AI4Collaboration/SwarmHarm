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


if __name__ == '__main__':
    unittest.main()
