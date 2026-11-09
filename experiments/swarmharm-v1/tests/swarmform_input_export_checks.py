"""Materialization check for the complete SwarmForm input matrix."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import export_swarmform_input_matrix


class SwarmFormInputExportChecks(unittest.TestCase):
    def test_all_one_hundred_input_packages_materialize(self):
        with TemporaryDirectory() as folder:
            output = Path(folder) / "matrix"
            export_swarmform_input_matrix.main(["--output", str(output)])
            index = json.loads((output / "index.json").read_text())
            self.assertEqual(index["input_environments"], 100)
            self.assertEqual(len(index["cells"]), 100)
            self.assertEqual(len({row["input_sha256"] for row in index["cells"]}), 100)
            self.assertEqual(len(list(output.rglob("input-package.json"))), 100)
            self.assertEqual(len(list(output.rglob("task.toml"))), 300)
            self.assertEqual(len(list(output.rglob("instruction.md"))), 300)


if __name__ == "__main__":
    unittest.main()
