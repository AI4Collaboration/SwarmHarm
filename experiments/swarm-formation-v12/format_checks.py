import json
from pathlib import Path
import tempfile
import unittest

import harbor_input
import lab
import schedule


class FormatChecks(unittest.TestCase):
    def test_harbor_packages_are_actual_runtime_inputs(self):
        counter = iter(range(10))
        plan = schedule.compile_plan(
            4, "control", lambda: f"worker-{next(counter):06d}"
        )[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashes = harbor_input.write(root, plan)
            audit = harbor_input.initial_audit(root, plan)
            self.assertEqual(sum(len(value) for value in hashes.values()), 4)
            for phase, actors in plan.items():
                for actor, item in actors.items():
                    self.assertEqual(audit[phase][actor]["input"][-1]["content"], lab.task(item))

    def test_claim_levels_are_explicit(self):
        contract = json.loads((Path(__file__).parent / "format-contract.json").read_text())
        self.assertEqual(contract["input"]["schema"], "1.4")
        self.assertEqual(contract["output"]["trajectory"], "ATIF-v1.8")
        self.assertTrue(contract["output"]["side_channel_chain_reviewed_independently"])
        self.assertFalse(contract["execution"]["generic_harbor_job_scheduler"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
