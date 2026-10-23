"""Collector utility controls; no model calls."""

from pathlib import Path
import inspect
import tempfile
import unittest
from unittest.mock import patch

import launch
import run
import schedule


class CollectorChecks(unittest.TestCase):
    def test_collector_resubmits_each_actor_without_a_global_round_barrier(self):
        source = inspect.getsource(run.collect)
        self.assertIn("future=next(as_completed(tuple(futures)))", source)
        self.assertNotIn("for future in as_completed(futures)", source)

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
        root = Path("/tmp/swarmharm-formation-v10")
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
                run.prepare(root, registration, key, 4, 4)
            reg = run.load(root / "registration.json")
            natural = reg["plan"]["natural"]
            self.assertEqual(len(natural), 4)
            self.assertEqual([item["arrival"] for item in natural.values()], list(range(4)))
            self.assertTrue(all("wave" not in item and "role" not in item for item in natural.values()))
            self.assertTrue(all("holder" not in key for item in natural.values() for key in item))
            self.assertEqual(reg["input_contract"], {
                "dedicated_communication_api": False,
                "preassigned_roles": False,
                "preassigned_pairs": False,
                "cooperation_instruction": False,
                "pressure": False,
                "peer_announcement": False,
                "vulnerability_hint": False,
                "seeded_peer_content": False,
                "shared_write_documented": False,
            })
            self.assertTrue(reg["honest_stop_available"])
            self.assertEqual(reg["pressure"], "none")
            self.assertNotIn("max_responses_per_actor", reg["budget"])
            self.assertNotIn("max_tools_per_actor", reg["budget"])
            self.assertEqual(reg["budget"]["active_contexts_natural"], 4)
            self.assertEqual(reg["budget"]["provider_concurrency"], 4)
            self.assertTrue(reg["connected_protocol"]["overlapping_execution"])
            self.assertIsNone(reg["per_agent_response_limit"])
            self.assertIsNone(reg["per_agent_tool_limit"])
            self.assertIsNone(reg["topology"])
            self.assertFalse(reg["topology_research_question"])
            self.assertIn("`deepseek/deepseek-v4.1-flash-1017`", (registration / "PROTOCOL.md").read_text())
            self.assertEqual(run.sha(root / "registration.json"), run.sha(registration / "registration.json"))

    def test_prepare_rejects_serial_or_underfilled_canonical_runs(self):
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
                with self.assertRaisesRegex(ValueError, "requires between four"):
                    run.prepare(root, registration, key, 4, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
