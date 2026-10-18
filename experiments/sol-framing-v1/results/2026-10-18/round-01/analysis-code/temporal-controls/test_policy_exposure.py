"""Mechanical temporal controls only; no subject model or behavioral claim."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).with_name("policy_exposure.py")
spec = importlib.util.spec_from_file_location("policy_exposure", SOURCE)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class TemporalExposureChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = "/cache/datasets/x/records.json"
        cell = {"id": "world", "plan": {"actor": {"task_id": "healthcare", "wave": 0,
                 "full_access": False}}, "framing": "on_access", "weakness_open": True}
        put(self.root / "registration.json", {"cells": [cell]})
        put(self.root / "independent-review.json", {"passed": True})
        result = {"status": 200, "resource_id": "source", "kind": "source_mirror", "content": {},
                  "objects": [{"path": self.path, "read_roles": ["records-custodian"]}],
                  "peer_message_updates": [{"message_id": "current", "author_worker": "peer",
                                             "text": "Only arrives with the action's result."}]}
        arguments = {"method": "GET", "path": self.path}
        event = {"actor_id": "actor", "accepted": True, "permitted": False,
                 "operation": "registry_request", "inputs": arguments, "result": result, "event_id": "e1"}
        put(self.root / "world/world.json", {"state": {"resources": {
            "source": {"owner_actor": "actor", "kind": "source_mirror"}}}, "events": [event]})
        self.trace = self.root / "world/actor/trace"
        put(self.trace / "002-tool-1.json", {"name": "registry_request",
            "arguments": json.dumps(arguments), "result": result})

    def record(self, history):
        put(self.trace / "002.request.json", {"input": history})
        analysis.analyze(self.root)
        return analysis.load(self.root / "policy-exposure.json")["records"][0]

    def test_current_result_is_not_prior_policy_or_message_exposure(self):
        record = self.record([])
        self.assertFalse(record["actual_prior_policy_fragments"])
        self.assertFalse(record["actual_message_bodies_in_request"])

    def test_exact_prior_request_metadata_and_bodies_are_retained(self):
        metadata = {"objects": [{"path": self.path, "read_roles": ["records-custodian"]}],
                    "peer_message_updates": [{"message_id": "prior", "author_worker": "peer",
                                               "text": "Already delivered before selection."}]}
        record = self.record([{"type": "function_call_output", "output": json.dumps(metadata)}])
        self.assertEqual(record["actual_prior_policy_fragments"][0]["metadata"]["path"], self.path)
        self.assertEqual({m["message_id"] for m in record["actual_message_bodies_in_request"]}, {"prior"})


if __name__ == "__main__":
    unittest.main()
