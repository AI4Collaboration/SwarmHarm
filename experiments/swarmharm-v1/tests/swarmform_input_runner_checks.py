"""Coverage checks for the 100 SwarmForm input witness routes."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from check_swarmform_input_runners import matrix


class SwarmFormInputRunnerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = matrix()

    def test_all_cells_have_a_concrete_runner(self):
        self.assertEqual(len(self.rows), 100)
        self.assertEqual(len({row["matrix_cell"] for row in self.rows}), 100)
        self.assertTrue(all((ROOT / row["runner"][0]).is_file() for row in self.rows))

    def test_all_deployment_encoding_mechanisms_are_routed(self):
        self.assertEqual(
            len({(row["deployment"], row["encoding"]) for row in self.rows}),
            25,
        )

    def test_runners_are_offline_witnesses(self):
        self.assertTrue(all(row["model_calls"] == 0 for row in self.rows))
        self.assertFalse(any("run_swarmform.py" in part
                             for row in self.rows for part in row["runner"]))


if __name__ == "__main__":
    unittest.main()
