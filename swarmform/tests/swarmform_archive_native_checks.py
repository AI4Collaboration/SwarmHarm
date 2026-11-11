"""Actual native threads and archive deployment against a local provider fixture."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'swarmform'/'scripts'))
from check_swarmform_archive_native import check

class ArchiveNativeChecks(unittest.TestCase):
    def test_scoped_archive_keeps_threads_arrivals_and_actual_published_files(self):
        cases = [('openai/gpt-5.6-sol','content',True,False),
                 ('openai/gpt-6.1-sol','metadata',True,True),
                 ('openai/gpt-5.6-sol','metadata',False,False),
                 ('openai/gpt-6.1-sol','content',False,True)]
        for model,profile,shared,wait in cases:
            with self.subTest(model=model,profile=profile,shared=shared), tempfile.TemporaryDirectory() as directory:
                result = check(Path(directory)/'run',model=model,profile=profile,
                               shared=shared,wait_for_arrivals=wait)
                self.assertEqual(result['correct_archived_deliveries'],9)
                self.assertTrue(result['atif_continuity_passed'])

if __name__=='__main__':unittest.main()
