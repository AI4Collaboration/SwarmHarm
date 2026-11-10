"""The file-edit command named by native instructions must actually work."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import workstation
import workstation_patch


class WorkstationPatchChecks(unittest.TestCase):
    def run_patch(self, cwd, body):
        return subprocess.run([sys.executable, workstation_patch.__file__],
            input='*** Begin Patch\n'+body+'\n*** End Patch\n', text=True,
            capture_output=True, cwd=cwd)

    def test_create_update_move_and_delete(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            result=self.run_patch(root, '*** Add File: nested/report.txt\n+one\n+two')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root/'nested/report.txt').read_text(), 'one\ntwo')
            result=self.run_patch(root,
                '*** Update File: nested/report.txt\n*** Move to: ready.txt\n@@\n one\n-two\n+三')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root/'nested/report.txt').exists())
            self.assertEqual((root/'ready.txt').read_text(), 'one\n三')
            result=self.run_patch(root, '*** Delete File: ready.txt')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root/'ready.txt').exists())

    def test_invalid_context_returns_failure_without_changing_file(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'report.txt'; path.write_text('original\n')
            result=self.run_patch(folder, '*** Update File: report.txt\n@@\n-missing\n+new')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_text(), 'original\n')

    def test_absolute_paths_and_argument_input(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'record.jsonl'
            patch='*** Begin Patch\n*** Add File: '+str(path)+'\n+{"state":"draft"}\n*** End Patch\n'
            result=subprocess.run([sys.executable, workstation_patch.__file__,patch],
                text=True,capture_output=True,cwd=folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_text(), '{"state":"draft"}')

    def test_missing_input_returns_failure(self):
        with TemporaryDirectory() as folder:
            result=subprocess.run([sys.executable,workstation_patch.__file__],
                input='',text=True,capture_output=True,cwd=folder)
            self.assertNotEqual(result.returncode, 0)

    def test_patch_roundtrip_through_workstation(self):
        station=workstation.Workstation({'/workspace/check.txt':workstation.ENCODE('draft\n')})
        try:
            result,snapshot=station.execute("apply_patch <<'PATCH'\n*** Begin Patch\n*** Update File: /workspace/check.txt\n@@\n-draft\n+ready\n*** End Patch\nPATCH",{})
            self.assertEqual(result['exit_code'],0,result)
            self.assertEqual(workstation.DECODE(snapshot['/workspace']['/workspace/check.txt']), 'ready\n')
            result,_=station.execute("apply_patch <<'PATCH'\n*** Begin Patch\n*** Add File: /etc/swarmharm-patch-test\n+outside writable workspace\n*** End Patch\nPATCH",{})
            self.assertNotEqual(result['exit_code'],0,result)
        finally:
            station.close()
