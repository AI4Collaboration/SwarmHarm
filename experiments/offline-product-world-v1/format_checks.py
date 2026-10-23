"""Executable Harbor input and planned-output contract for the product world."""
import json
from pathlib import Path
import tomllib
import unittest
from harbor.models.task.config import TaskConfig

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TASK = REPO / "tasks/product-world/model-release-v1"


class FormatChecks(unittest.TestCase):
    def test_harbor_task(self):
        config = TaskConfig.model_validate(tomllib.loads((TASK / "task.toml").read_text()))
        self.assertEqual(config.environment.network_mode.value, "no-network")
        self.assertEqual(config.agent.user, "65534")
        self.assertTrue((TASK / "instruction.md").read_text().startswith("Please complete"))

    def test_output_claim_stays_future_tense(self):
        contract = json.loads((HERE / "format-contract.json").read_text())
        self.assertEqual(contract["output"]["trajectory"], "ATIF-v1.8")
        self.assertIn("not claimed", contract["claims"]["harbor_native_execution"])
        self.assertIn("not claimed", contract["claims"]["schema_valid_output"])


if __name__ == "__main__": unittest.main(verbosity=2)
