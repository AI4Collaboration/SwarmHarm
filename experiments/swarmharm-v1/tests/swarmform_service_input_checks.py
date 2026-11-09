"""Service-backed SwarmForm input coverage checks; no model calls."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from check_swarmform_service_inputs import ENCODINGS, validate_matrix


class ServiceInputChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.report = validate_matrix(Path(cls.temp.name) / "matrix.json")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_forty_service_inputs_build(self):
        self.assertTrue(self.report["passed"])
        self.assertEqual(self.report["cells"], 40)
        self.assertEqual(len(self.report["rows"]), 40)

    def test_both_deployments_cover_the_five_canonical_encodings(self):
        self.assertEqual(
            {(row["deployment"], row["encoding"]) for row in self.report["rows"]},
            {(deployment, encoding)
             for deployment in ("artifact_namespace", "job_namespace")
             for encoding in ENCODINGS},
        )

    def test_scope_does_not_change_worker_visible_input(self):
        self.assertTrue(all(row["matched_private_worker_input"]
                            for row in self.report["rows"]))


if __name__ == "__main__":
    unittest.main()
