"""Archived bytes must be complete before optional raw removal."""
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
loader = SourceFileLoader('archive_trajectories', str(ROOT/'scripts/archive-trajectories'))
spec = importlib.util.spec_from_loader(loader.name, loader)
archive = importlib.util.module_from_spec(spec)
loader.exec_module(archive)


class ArchiveChecks(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)/'cohort'
        root.mkdir()
        (root/'summary.json').write_text('{"complete": true, "reason":"all_finished"}')
        (root/'registration.json').write_text('{"model":"fixture", "population":4}')
        (root/'actor.jsonl').write_text('original event\n'*1000)
        (root/'evidence-manifest.json').write_text(json.dumps(archive.inventory(root)))
        return root

    def test_current_swarmform_trace_can_be_archived_without_a_legacy_manifest(self):
        with TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root/'evidence-manifest.json').unlink()
            (root/'summary.json').write_text(json.dumps(dict(schema='swarmform-completion-v1',
                                                              complete=True, physical_stop_verified=True)))
            (root/'physical-stop.json').write_text('{"research_stop_verified": true}')
            (root/'inputs.json').write_text('{"prompts": {"actor": []}}')
            for name in ('observations.jsonl.gz', 'outcomes.json', 'truth.json'):
                (root/name).touch()
            with self.assertRaisesRegex(ValueError, 'missing trace'):
                archive.archive_run(root, remove_source=True)
            (root/'actor.jsonl').rename(root/'actor.jsonl.gz')
            row = archive.archive_run(root, remove_source=True)
            self.assertTrue(Path(row['archive']).is_file())
            self.assertFalse(root.exists())

    def test_archive_and_remove_keeps_every_original_byte(self):
        with TemporaryDirectory() as directory:
            root = self.fixture(directory)
            before = archive.inventory(root)
            row = archive.archive_run(root, remove_source=True)
            self.assertFalse(root.exists())
            self.assertTrue(row['raw_removed'])
            self.assertEqual(row['sha256'], archive.digest(Path(row['archive'])))
            with tarfile.open(row['archive']) as bundle:
                actual = {m.name: hashlib.sha256(bundle.extractfile(m).read()).hexdigest()
                          for m in bundle}
            self.assertEqual(actual, before)
            self.assertEqual(json.loads((Path(directory)/'cohort.archive.json').read_text())['files'], before)

    def test_manifest_mismatch_and_symlinks_preserve_raw_data(self):
        with TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root/'actor.jsonl').write_text('modified')
            with self.assertRaisesRegex(ValueError, 'manifest'):
                archive.archive_run(root, remove_source=True)
            self.assertTrue(root.exists())
            self.assertFalse(list(Path(directory).glob('*.tar.gz')))
            (root/'link').symlink_to(root/'actor.jsonl')
            with self.assertRaisesRegex(ValueError, 'regular files'):
                archive.archive_run(root)

    def test_another_archive_writer_is_left_alone(self):
        with TemporaryDirectory() as directory:
            root = self.fixture(directory)
            staging = root.with_name('cohort.tar.partial')
            staging.write_bytes(b'other writer')
            with self.assertRaises(FileExistsError):
                archive.archive_run(root, remove_source=True)
            self.assertEqual(staging.read_bytes(), b'other writer')
            self.assertTrue(root.exists())

    def test_native_manifest_shape_and_duplicate_archive(self):
        with TemporaryDirectory() as directory:
            root = self.fixture(directory)
            manifest = json.loads((root/'evidence-manifest.json').read_text())
            (root/'evidence-manifest.json').write_text(json.dumps({'files': manifest}))
            archive.archive_run(root)
            self.assertTrue(root.exists())
            with self.assertRaises(FileExistsError):
                archive.archive_run(root, remove_source=True)
            self.assertTrue(root.exists())


if __name__ == '__main__':
    unittest.main()
