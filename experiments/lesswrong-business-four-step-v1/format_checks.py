"""Harbor-input assertions for the frozen four-step plan."""
import tempfile
import unittest
from pathlib import Path
import harbor_input,lab

class FormatChecks(unittest.TestCase):
    def test_packages_are_schema_valid_and_exact_runtime_inputs(self):
        plan={f'{s}-001':lab.item(s,1) for s in lab.STEPS}
        with tempfile.TemporaryDirectory() as temp:
            records=harbor_input.write(Path(temp),plan);self.assertEqual(set(records),set(plan))
            for actor,value in plan.items():self.assertTrue(harbor_input.validate(Path(temp)/actor,value,actor))
    def test_contract_keeps_input_execution_and_output_claims_separate(self):
        import json
        value=json.loads((Path(__file__).with_name('format-contract.json')).read_text())
        self.assertEqual(value['input']['schema'],'1.4');self.assertFalse(value['execution']['generic_harbor_job_scheduler']);self.assertEqual(value['output']['trajectory'],'ATIF-v1.8')

if __name__=='__main__':unittest.main(verbosity=2)
