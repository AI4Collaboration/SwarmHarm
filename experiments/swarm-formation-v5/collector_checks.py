"""Collector utility controls; no model calls."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import launch
import run
import schedule


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

    def test_response_must_match_the_frozen_model(self):
        request = {"model": "z-ai/glm-5.3-flashx"}
        run.validate_response_model(request, {"model": "z-ai/glm-5.3-flashx"})
        with self.assertRaises(ValueError):
            run.validate_response_model(request, {"model": "~z-ai/glm-flash-latest"})

    def test_launcher_forwards_registration_and_host_only_key(self):
        root = Path("/tmp/swarmharm-formation-v5")
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
            with patch.object(run, "verify_routes", return_value=routes):
                run.prepare(root, registration, key, 6, 2)
            reg = run.load(root / "registration.json")
            natural = reg["plan"]["natural"]
            self.assertEqual(len(natural), 6)
            self.assertEqual([sum(item["wave"] == wave for item in natural.values()) for wave in range(3)], [2, 2, 2])
            self.assertTrue(all("role" not in item for item in natural.values()))
            self.assertTrue(all("holder" not in key for item in natural.values() for key in item))
            self.assertEqual(reg["input_contract"], {
                "dedicated_communication_api": False,
                "preassigned_roles": False,
                "preassigned_pairs": False,
                "cooperation_instruction": False,
                "pressure": False,
                "peer_announcement": False,
                "vulnerability_hint": False,
            })
            self.assertEqual(reg["pressure"], "none")
            self.assertIn("`deepseek/deepseek-v4.1-flash-1017`", (registration / "PROTOCOL.md").read_text())
            self.assertEqual(run.sha(root / "registration.json"), run.sha(registration / "registration.json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
