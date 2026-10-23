"""Collector utility controls; no model calls."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import launch
import run
import topology


class CollectorChecks(unittest.TestCase):
    def test_retry_classification(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "error.json"
            run.save(path, {"http_status": 422})
            self.assertFalse(run.retryable_transport_error(RuntimeError("422"), path))
            run.save(path, {"http_status": 429})
            self.assertTrue(run.retryable_transport_error(RuntimeError("429"), path))

    def test_empty_preflight_arguments_accept_provider_wrapper(self):
        self.assertTrue(run.empty_tool_arguments("{}"))
        self.assertTrue(run.empty_tool_arguments('{"parameters":{}}'))
        self.assertFalse(run.empty_tool_arguments('{"unexpected":1}'))

    def test_launcher_forwards_registration_and_host_only_key(self):
        root = Path("/tmp/swarmharm-formation-v1")
        registration = Path("/tmp/swarmharm-formation-registration")
        key = Path("/tmp/axonhub.key")
        argv = launch.collector_command(root, registration, key)
        self.assertIn(str(root.resolve()), argv)
        self.assertIn(str(registration.resolve()), argv)
        self.assertEqual(argv[-2:], ["--key-file", str(key.resolve())])

    def test_prepare_freezes_population_without_organizational_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "study"
            registration = Path(temporary) / "registration"
            key = Path(temporary) / "key"
            key.write_text("test-key")
            routes = {
                "checked_at": "test", "model": "deepseek/deepseek-v4.1-flash-1017",
                "openrouter": {"http_status": 200, "model_found": True, "model_count": 1},
                "axonhub": {"http_status": 200, "model_found": True, "model_count": 1},
            }
            spec = topology.default_spec(3, "ring")
            with patch.object(run, "verify_routes", return_value=routes):
                run.prepare(root, registration, key, spec)
            reg = run.load(root / "registration.json")
            natural = reg["plan"]["natural"]
            self.assertEqual(len(natural), 3)
            self.assertTrue(all(item["wave"] == 0 for item in natural.values()))
            self.assertTrue(all("role" not in item for item in natural.values()))
            self.assertTrue(all("holder" not in key for item in natural.values() for key in item))
            self.assertEqual(reg["input_contract"], {
                "preassigned_roles": False,
                "preassigned_pairs": False,
                "cooperation_instruction": False,
            })
            self.assertEqual(reg["pressure"], "none")
            self.assertEqual(run.sha(root / "registration.json"), run.sha(registration / "registration.json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
