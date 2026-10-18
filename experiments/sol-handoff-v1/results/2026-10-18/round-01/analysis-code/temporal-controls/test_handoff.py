"""Temporal and origin checks; no model calls or behavioral claims."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("handoff", Path(__file__).with_name("handoff.py"))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class ActualInputChecks(unittest.TestCase):
    def setUp(self):
        self.state = {"actors": {"a": {"worker": "worker-a"}, "b": {"worker": "worker-b"}},
                      "resources": {"note": {"owner_actor": "b", "kind": "work_artifact"},
                                    "receipt": {"owner_actor": "b", "kind": "work_receipt"}}}

    def test_initial_metadata_and_read_receipt_are_not_peer_authored_methods(self):
        value = {"kind": "work_receipt", "resource_id": "receipt", "content": {"path": "/cache/data"}}
        request = {"input": [{"role": "developer", "content": json.dumps({"recent_work_index": [{"resource_id": "note"}]})},
                             {"type": "function_call_output", "output": json.dumps(value)}]}
        self.assertEqual(handoff.peer_inputs(request, "a", self.state), [])

    def test_only_actual_prior_peer_text_and_exact_version_count(self):
        request = {"input": [{"type": "function_call_output", "output": json.dumps({
            "kind": "work_artifact", "resource_id": "note", "content": "old body",
            "peer_message_updates": [{"message_id": "m", "author_worker": "worker-b", "text": "real prior body"},
                                     {"message_id": "own", "author_worker": "worker-a", "text": "own text"}]})}]}
        actual = handoff.peer_inputs(request, "a", self.state)
        self.assertEqual({x["kind"] for x in actual}, {"chat", "work_artifact"})
        self.assertEqual({x["text"] for x in actual}, {"old body", "real prior body"})
        self.assertNotEqual(handoff.digest("old body"), handoff.digest("later overwritten body"))
        self.assertEqual(handoff.peer_inputs({"input": []}, "a", self.state), [])

    def test_genuine_historical_posts_are_not_live_peer_messages(self):
        request = {"input": [{"type": "function_call_output", "output": json.dumps({
            "kind": "archive_reference", "resource_id": "old-thread", "content": {
                "type": "historical_reference", "live_peer": False,
                "messages": [{"message_id": "old-m", "author_worker": "worker-b", "text": "Real old post"}]}})}]}
        self.assertEqual(handoff.peer_inputs(request, "a", self.state), [])


if __name__ == "__main__": unittest.main()
