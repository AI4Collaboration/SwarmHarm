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

    def test_checks_reused_only_when_required_modules_are_covered(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'registration-seal.json').write_text('{}')
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

    def test_missing_archive_never_restarts_collection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'cohort'
            root.with_name('cohort.archive.json').write_text(json.dumps(
                {'archive': str(root)+'.tar.gz', 'sha256':'fixture'}))
            self.assertEqual(batch.existing_status(root)['status'], 'archive_missing')


if __name__ == '__main__':
    unittest.main()
