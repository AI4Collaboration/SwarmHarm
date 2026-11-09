"""Minimal structural checks for the SwarmForm input matrix."""

import ast
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from check_swarmform_input_runners import matrix
import export_swarmform_input_matrix as exporter
from swarmform.input_catalog import build
import swarmform_ipc_witness_protocols as ipc_protocols
import swarmform_service_witness_codecs as service_protocols


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

    def test_each_backend_builds_three_matched_workstations(self):
        connection = {
            "shared_files": "/workspace/work-order.md",
            "shared_ipc": "/workspace/processor.json",
            "worker_endpoint": "/workspace/processor.json",
            "artifact_namespace": "/workspace/archive.json",
            "job_namespace": "/workspace/processing.json",
        }
        for deployment, expected in connection.items():
            with self.subTest(deployment=deployment):
                visible, truth, _ = build(
                    "november", "Data Analysis", deployment=deployment,
                    encoding="payload_content", shared=True)
                private = build(
                    "november", "Data Analysis", deployment=deployment,
                    encoding="payload_content", shared=False)
                self.assertEqual((visible, truth), private[:2])
                self.assertEqual(len(visible["startup"]), 3)
                self.assertTrue(all(expected in files
                                    for files in visible["startup"].values()))

    def test_operator_witness_protocols_parse(self):
        snippets = [value for module in (ipc_protocols, service_protocols)
                    for name, value in vars(module).items()
                    if name.isupper() and isinstance(value, str)]
        self.assertEqual(len(snippets), 16)
        for index, snippet in enumerate(snippets):
            ast.parse(snippet, filename=f"witness-protocol-{index}")

    def test_exporter_materializes_one_real_cell_and_indexes_all_cells(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            package = exporter.materialize(
                root / "one", "november", "job_namespace", "timing",
                "Knowledge Work")
            cell = root / "one" / "job_namespace" / "timing" / "knowledge-work"
            self.assertEqual(package["population"], 3)
            self.assertEqual(len(list(cell.rglob("task.toml"))), 3)
            self.assertEqual(len(list(cell.rglob("instruction.md"))), 3)

            def fake_materialize(output, dataset, deployment, encoding, domain):
                key = "/".join((deployment, encoding, domain))
                return {"matrix_cell": key,
                        "input_sha256": sha256(key.encode()).hexdigest()}

            with patch.object(exporter, "materialize", side_effect=fake_materialize) as mocked:
                exporter.main(["--output", str(root / "matrix")])
            index = json.loads((root / "matrix" / "index.json").read_text())
            self.assertEqual(mocked.call_count, 100)
            self.assertEqual(index["input_environments"], 100)


if __name__ == "__main__":
    unittest.main()
