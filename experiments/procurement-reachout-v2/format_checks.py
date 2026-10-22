"""Executable input/output format controls."""
import json
from pathlib import Path
import tempfile
import unittest
import harbor_input

class FormatChecks(unittest.TestCase):
    def test_contract_and_harbor_input(self):
        contract=json.loads((Path(__file__).parent/'format-contract.json').read_text())
        self.assertEqual(contract['input']['schema'],'1.4')
        self.assertFalse(contract['execution']['generic_harbor_job_scheduler'])
        self.assertEqual(contract['output']['trajectory'],'ATIF-v1.8')
        with tempfile.TemporaryDirectory() as folder:
            actors=['RA-17','RA-18'];records=harbor_input.write(folder,actors)
            self.assertEqual(set(records),set(actors));self.assertEqual(set(harbor_input.audit(folder,actors)),set(actors))

if __name__=='__main__':unittest.main(verbosity=2)
