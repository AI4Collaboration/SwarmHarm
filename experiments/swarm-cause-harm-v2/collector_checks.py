"""Collector controls; no model calls."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import launch
import run


class CollectorChecks(unittest.TestCase):
    def test_retry_classification(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "error.json"
            run.save(path, {"http_status": 422})
            self.assertFalse(run.retryable_transport_error(RuntimeError("422"), path))
            run.save(path, {"http_status": 429})
            self.assertTrue(run.retryable_transport_error(RuntimeError("429"), path))

    def test_response_model_is_exact(self):
        request = {"model": "deepseek/deepseek-v4.1-flash-1017"}
        run.validate_response_model(request, {"model": request["model"]})
        with self.assertRaises(ValueError):
            run.validate_response_model(request, {"model": "deepseek/deepseek-chat"})

    def test_prepare_freezes_two_unaware_source_agents_and_fresh_successor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "study"
            registration = Path(temporary) / "registration"
            key = Path(temporary) / "key"
            key.write_text("test-key")
            routes = {
                "checked_at": "test",
                "model": "deepseek/deepseek-v4.1-flash-1017",
                "openrouter": {"http_status": 200, "model_found": True, "model_count": 1},
                "axonhub": {"http_status": 200, "model_found": True, "model_count": 1},
            }
            with patch.object(run, "verify_routes", return_value=routes):
                run.prepare(root, registration, key)
            frozen = run.load(root / "registration.json")
            plan = frozen["plan"]["natural"]
            self.assertEqual(len(plan), 3)
            self.assertEqual([item["wave"] for item in plan.values()], [0, 0, 1])
            self.assertEqual(len({item["group_id"] for item in plan.values()}), 2)
            self.assertEqual([item["line_indices"] for item in plan.values()], [[0], [1], [0, 1]])
            self.assertEqual(frozen["pressure"], "none")
            self.assertNotIn("max_responses_per_actor", frozen["budget"])
            self.assertNotIn("max_tools_per_actor", frozen["budget"])
            self.assertIsNone(frozen["per_agent_response_limit"])
            self.assertIsNone(frozen["per_agent_tool_limit"])
            self.assertTrue(all(value is False for value in frozen["input_contract"].values()))
            self.assertIn("`deepseek/deepseek-v4.1-flash-1017`", (registration / "PROTOCOL.md").read_text())

    def test_launcher_forwards_host_only_key(self):
        root = Path("/tmp/swarm-cause-harm-v2")
        registration = Path("/tmp/swarm-cause-harm-registration")
        key = Path("/tmp/axonhub.key")
        argv = launch.collector_command(root, registration, key)
        self.assertIn(str(root.resolve()), argv)
        self.assertEqual(argv[-2:], ["--key-file", str(key.resolve())])


if __name__ == "__main__":
    unittest.main(verbosity=2)

