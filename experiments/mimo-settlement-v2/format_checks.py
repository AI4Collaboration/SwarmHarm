"""Executable Harbor/ATIF contract checks for settlement v2."""
import json
from pathlib import Path
import tomllib
import unittest

from harbor.models.task.config import TaskConfig

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TASK = REPO / "tasks/mimo-payment/settled-disbursement-v2"


class FormatChecks(unittest.TestCase):
    def test_harbor_task_is_the_runtime_input(self):
        config = TaskConfig.model_validate(tomllib.loads((TASK / "task.toml").read_text()))
        self.assertEqual(config.environment.network_mode, "no-network")
        instruction = (TASK / "instruction.md").read_text().strip()
        self.assertTrue(instruction.startswith("Please finalize the City of Fayetteville"))

    def test_claim_levels_are_explicit(self):
        contract = json.loads((HERE / "format-contract.json").read_text())
        self.assertEqual(contract["input"]["schema"], "1.4")
        self.assertEqual(contract["output"]["trajectory"], "ATIF-v1.8")
        self.assertTrue(contract["execution"]["generic_harbor_job_scheduler"])


if __name__ == "__main__":
    unittest.main()
