import json
from pathlib import Path
import tempfile
import unittest

import harbor_input
import lab
import run

class FormatChecks(unittest.TestCase):
    def test_harbor_packages_are_the_actual_runtime_inputs(self):
        plan=run.make_plan(lab.mechanics.fixtures())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);hashes=harbor_input.write(root,plan)
            audit=harbor_input.initial_audit(root,plan)
            self.assertEqual(sum(len(v) for v in hashes.values()),6)
            for phase,actors in plan.items():
                for actor,item in actors.items():
                    self.assertEqual(audit[phase][actor]['input'][-1]['content'],lab.task(item))

    def test_claim_levels_are_explicit(self):
        contract=json.loads((Path(__file__).parent/'format-contract.json').read_text())
        self.assertEqual(contract['input']['schema'],'1.4')
        self.assertEqual(contract['output']['trajectory'],'ATIF-v1.8')
        self.assertFalse(contract['execution']['generic_harbor_job_scheduler'])

if __name__=='__main__':unittest.main()
