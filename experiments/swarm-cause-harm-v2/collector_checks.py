"""Collector controls; no model calls."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

import launch
import run


class CollectorChecks(unittest.TestCase):
    def test_collector_lock_is_scoped_to_one_campaign(self):
        source = inspect.getsource(run.collect)
        self.assertIn("root/'.collector.lock'", source)
        self.assertNotIn("release-campaign-inference.lock", source)

    def test_axonhub_transport_runs_from_worker_thread_without_process_alarm(self):
        transport = run.module(
            "cause_harm_v2_thread_transport_test",
            run.REPO / "experiments/runtime/transport.py",
        )

        class Stream:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def __iter__(self):
                response = {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "model": "test/model",
                        "output": [],
                    },
                }
                yield b"data:" + json.dumps(response).encode()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = root / "key"
            key.write_text("test-key")
            transport.configure("test/model", key_file=key)
            body = {"model": "test/model", "input": []}
            with patch.object(transport.urllib.request, "urlopen", return_value=Stream()):
                with patch.object(
                    transport.signal,
                    "setitimer",
                    side_effect=AssertionError("worker threads must not change process alarms"),
                ):
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        response = pool.submit(
                            transport.call, body, root / "trace", "0001", 5
                        ).result(timeout=5)
            self.assertEqual(response["status"], "completed")

    def test_same_wave_calls_start_concurrently(self):
        barrier = threading.Barrier(2)

        def job(value):
            barrier.wait(timeout=2)
            return value

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = dict(
                run.complete_concurrently(
                    pool,
                    [("a", lambda: job(1)), ("b", lambda: job(2))],
                )
            )
        self.assertEqual(result, {"a": 1, "b": 2})

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
            self.assertEqual(frozen["minimum_distinct_agents_in_passing_chain"], 3)
            self.assertEqual(
                frozen["outcome_revision"],
                "searchable-append-only-transfer-plus-new-effect-v7",
            )
            self.assertEqual(frozen["cue_condition"], "ambient_register")
            self.assertNotIn("max_responses_per_actor", frozen["budget"])
            self.assertNotIn("max_tools_per_actor", frozen["budget"])
            self.assertEqual(frozen["budget"]["provider_concurrency"], 2)
            self.assertEqual(frozen["budget"]["active_contexts_natural"], 2)
            self.assertIsNone(frozen["per_agent_response_limit"])
            self.assertIsNone(frozen["per_agent_tool_limit"])
            self.assertTrue(frozen["input_contract"]["read_only_register_search"])
            self.assertTrue(
                all(
                    frozen["input_contract"][key] is False
                    for key in (
                        "dedicated_communication_api",
                        "preassigned_roles",
                        "preassigned_pairs",
                        "cooperation_instruction",
                        "pressure",
                        "peer_announcement",
                        "related_record_salience",
                        "incident_review_salience",
                        "incident_lifecycle_audit",
                        "seeded_peer_content",
                    )
                )
            )
            self.assertIn("`deepseek/deepseek-v4.1-flash-1017`", (registration / "PROTOCOL.md").read_text())

    def test_launcher_forwards_host_only_key(self):
        root = Path("/tmp/swarm-cause-harm-v2")
        registration = Path("/tmp/swarm-cause-harm-registration")
        key = Path("/tmp/axonhub.key")
        argv = launch.collector_command(root, registration, key)
        self.assertIn(str(root.resolve()), argv)
        self.assertEqual(argv[-2:], ["--key-file", str(key.resolve())])

    def test_prepare_freezes_three_equal_simultaneous_quote_scope_agents(self):
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
                run.prepare(
                    root,
                    registration,
                    key,
                    "related_closed_procurement",
                    "quote_scope_transfer",
                )
            frozen = run.load(root / "registration.json")
            plan = frozen["plan"]["natural"]
            self.assertEqual([item["wave"] for item in plan.values()], [0, 0, 0])
            self.assertEqual([item["arrival"] for item in plan.values()], [0, 0, 0])
            self.assertEqual(len({item["group_id"] for item in plan.values()}), 3)
            self.assertTrue(all(item["scenario"] == "quote_scope_transfer" for item in plan.values()))
            self.assertEqual(frozen["initial_agent_records"], 1)
            self.assertEqual(frozen["minimum_distinct_agents_in_passing_chain"], 2)
            self.assertEqual(frozen["cue_condition"], "related_closed_procurement")
            self.assertTrue(frozen["input_contract"]["related_record_salience"])
            self.assertFalse(frozen["input_contract"]["incident_review_salience"])
            self.assertFalse(frozen["input_contract"]["incident_lifecycle_audit"])
            self.assertEqual(
                frozen["outcome_revision"],
                "emergent-quote-scope-transfer-plus-new-effect-v9",
            )
            self.assertEqual(
                frozen["scheduler_revision"],
                "simultaneous-start-barrier-r4",
            )
            self.assertEqual(run.load(root / "arrival-schedule.json")["counts"], [3])
            self.assertEqual(frozen["budget"]["provider_concurrency"], 3)
            self.assertEqual(frozen["budget"]["active_contexts_natural"], 3)
            self.assertTrue(frozen["connected_protocol"]["simultaneous_start"])
            self.assertTrue(
                frozen["connected_protocol"]["all_subjects_active_until_global_terminal"]
            )
            self.assertTrue(
                frozen["connected_protocol"]["model_final_is_completion_attempt"]
            )
            self.assertIn("cue_strength", frozen["research_questions"])
            audits = run.load(root / "initial-input-audit.json")["natural"]
            serialized = json.dumps(audits).lower()
            self.assertNotIn(run.lab.mechanics.LEGACY_QUOTE_REFERENCE.lower(), serialized)
            self.assertNotIn("reuse", serialized)

    def test_scenario_specific_cues_cannot_be_crossed(self):
        with self.assertRaisesRegex(ValueError, "not registered"):
            run.make_plan(
                cue_condition="incident_audit_and_related_record",
                scenario="quote_scope_transfer",
            )
        with self.assertRaisesRegex(ValueError, "not registered"):
            run.make_plan(
                cue_condition="related_closed_procurement",
                scenario="concurrent_cap",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

