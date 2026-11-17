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
    def test_resume_uses_retained_retry_without_renaming_or_restarting_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            row = dict(model='fixture', population=4, replicate=1, scenario='knowledge-work',
                       mechanism='task-gaming', source_sha256='old-source', seconds=3600)
            output = root/'fixture/n4/original-r2'
            output.mkdir(parents=True)
            (output/'completion.json').write_text('{"status":"provider_hold"}')
            original = (output/'completion.json').read_bytes()
            record = {**row, 'replicate':2, 'output':str(output),
                      'registration':'/original/registration', 'status':'provider_hold'}
            saved = {batch.batch_resume.key(row):dict(settings=row, path=str(output.relative_to(root)), record=record)}
            retained = batch.attempt_record(root, row, 'fixture', 'group', saved)
            self.assertEqual(retained['replicate'], 2)
            self.assertEqual(retained['selection_replicate'], 1)
            self.assertEqual(retained['output'], str(output))
            self.assertEqual(retained['registration'], '/original/registration')
            self.assertIsNotNone(batch.existing_status(Path(retained['output'])))
            self.assertEqual((output/'completion.json').read_bytes(), original)
            changed = {**row, 'seconds':7200}
            with self.assertRaisesRegex(ValueError, 'settings differ'):
                batch.attempt_record(root, changed, 'fixture', 'group', saved)
            record['output'] = str(root/'different')
            with self.assertRaisesRegex(ValueError, 'output differs'):
                batch.attempt_record(root, row, 'fixture', 'group', saved)

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
