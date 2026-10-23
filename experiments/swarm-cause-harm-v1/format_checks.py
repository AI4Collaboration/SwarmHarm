"""Harbor input and ATIF output contract controls."""

import json
from pathlib import Path
import tempfile
import unittest

import harbor_input
import lab
from checks import actor_plan


class FormatChecks(unittest.TestCase):
    def test_harbor_packages_are_runtime_inputs(self):
        plan = {"natural": actor_plan()}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashes = harbor_input.write(root, plan)
            audit = harbor_input.initial_audit(root, plan)
            self.assertEqual(sum(len(value) for value in hashes.values()), 2)
            for actor, item in plan["natural"].items():
                self.assertEqual(audit["natural"][actor]["input"][-1]["content"], lab.task(item))

    def test_claim_levels_are_explicit(self):
        contract = json.loads((Path(__file__).parent / "format-contract.json").read_text())
        self.assertEqual(contract["input"]["schema"], "1.4")
        self.assertEqual(contract["output"]["trajectory"], "ATIF-v1.8")
        self.assertTrue(contract["output"]["business_effect_reviewed_independently"])
        self.assertTrue(contract["output"]["method_adoption_reviewed_independently"])
        self.assertFalse(contract["execution"]["generic_harbor_job_scheduler"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

