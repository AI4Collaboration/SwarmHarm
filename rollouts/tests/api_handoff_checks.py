"""Portable matrix integrity and non-destructive resume, without inference."""
import json
import gzip
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from swarmform import formation_inputs as inputs
from swarmform.__main__ import CHANNELS

ROOT = Path(__file__).resolve().parents[2]


class APIHandoffChecks(unittest.TestCase):
    def plan(self, *args):
        result = subprocess.run([sys.executable, str(ROOT/'rollouts/run_matrix.py'),
                                 '--model', 'local-test-model', '--harness', 'chat-completions', *args],
                                capture_output=True, text=True, check=True, cwd=ROOT)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_default_matrix_and_task_material_match_across_channels(self):
        rows = self.plan()
        self.assertEqual(len(rows), 72)
        self.assertEqual(list(dict.fromkeys(r['population'] for r in rows)), [4, 8, 16])
        self.assertEqual(sum(row['population'] for row in rows), 672)
        self.assertTrue(all(row['names'] == 'numbered' for row in rows))

    def test_finished_or_archived_attempts_are_not_restarted(self):
        import hashlib
        args = ['--tasks', 'service-plan', '--populations', '4']
        rows = self.plan(*args)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for i, row in enumerate(rows):
                suffix = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
                out = root/'local-test-model'/'n4'/f"service-plan-{row['channel']}-r1-{suffix}"
                out.parent.mkdir(parents=True, exist_ok=True)
                if i == 0:
                    archive = out.with_suffix('.tar.gz')
                    archive.write_bytes(b'fixture')
                    out.with_name(out.name+'.archive.json').write_text(json.dumps(
                        {'archive': str(archive), 'sha256': 'fixture'}))
                else:
                    out.mkdir()
                    (out/'summary.json').write_text('{"complete": true, "physical_stop_verified": true}')
                    (out/'actor.jsonl.gz').write_bytes(gzip.compress(b'{}\n'))
                    (out/'evidence-manifest.json').write_text(json.dumps({
                        file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in out.iterdir()}))
            result = subprocess.run([sys.executable, str(ROOT/'rollouts/run_matrix.py'),
                                     '--model', 'local-test-model', '--harness', 'chat-completions', *args, '--execute', '--out', directory],
                                    capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads((root/'index.json').read_text())
            self.assertEqual(len(index['runs']), 4)
            self.assertEqual(index['runs'][0]['status'], 'archived')
            self.assertFalse(list(root.rglob('*.log')))
            incompatible = subprocess.run([sys.executable, str(ROOT/'rollouts/run_matrix.py'),
                '--model', 'changed-model', '--harness', 'chat-completions', *args, '--execute', '--out', directory],
                capture_output=True, text=True, cwd=ROOT)
            self.assertNotEqual(incompatible.returncode, 0)
            self.assertIn('different plan', incompatible.stderr)


if __name__ == '__main__':
    unittest.main()
