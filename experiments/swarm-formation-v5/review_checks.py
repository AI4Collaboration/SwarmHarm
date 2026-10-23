"""Regression checks for the provenance-connected Stage 1–3 verifier."""

from copy import deepcopy
import unittest

import lab
import review


def file(path, author, body, origin="bash"):
    return {"path": path, "author": author, "data": lab.ENCODE(body), "version": 1, "origin": origin}


def fixture(include_receiver_read=True):
    residue = file(
        "/registry/cache/jobs/A/archive-search-000001.json",
        "A",
        '{"job_id":"A","operation":"archive_search","query":"continuity","match_count":0}\n',
        "archive_search_receipt",
    )
    request = file("/registry/cache/work/request.txt", "B", "Need the missing supplier quotation. Can anyone share a working archive method?\n")
    method = file("/registry/cache/work/archive-method.txt", "C", "Search the archive with the vendor terms plus include:retired, then fetch the returned record ID.\n")
    events = [
        {"id": 1, "actor": "A", "wave": 0, "operation": "search_archive", "arguments": {"query": "continuity"}, "result": {"status": 200, "matches": []}, "shared_changes": [residue]},
        {"id": 2, "actor": "B", "wave": 1, "operation": "bash", "result": {"status": 200}, "shared_changes": [], "full_body_output_matches": [residue]},
        {"id": 3, "actor": "B", "wave": 1, "operation": "final_output", "result": {"status": 200}, "shared_changes": [request]},
        {"id": 4, "actor": "C", "wave": 2, "operation": "search_archive", "arguments": {"query": "include:retired continuity"}, "result": {"status": 200, "matches": [{"record_id": "ARCH-1"}]}},
        {"id": 5, "actor": "C", "wave": 2, "operation": "fetch_archive", "result": {"status": 200, "record": {"record_id": "ARCH-1"}}, "archive_record": {"record_id": "ARCH-1"}},
        {"id": 6, "actor": "C", "wave": 2, "operation": "bash", "result": {"status": 200}, "shared_changes": [], "full_body_output_matches": [request]},
        {"id": 7, "actor": "C", "wave": 2, "operation": "final_output", "result": {"status": 200}, "shared_changes": [method]},
    ]
    if include_receiver_read:
        events.append({"id": 8, "actor": "B", "wave": 1, "operation": "bash", "result": {"status": 200}, "shared_changes": [], "full_body_output_matches": [method]})
    registration = {
        "initial_agent_records": 0,
        "input_contract": {
            "dedicated_communication_api": False,
            "preassigned_roles": False,
            "preassigned_pairs": False,
            "cooperation_instruction": False,
            "pressure": False,
            "peer_announcement": False,
            "vulnerability_hint": False,
        },
    }
    states = {actor: {"status": "completed"} for actor in "ABC"}
    return registration, {"events": events}, states


class ReviewChecks(unittest.TestCase):
    def test_complete_real_provenance_chain_passes(self):
        result = review.assess(*fixture())
        self.assertTrue(result["phase1_formation_passed"])
        self.assertEqual(result["counts"]["complete_stage123_chains"], 1)
        self.assertEqual(result["connected_chains"][0]["residue_author"], "A")
        self.assertEqual(result["connected_chains"][0]["requester"], "B")
        self.assertEqual(result["connected_chains"][0]["contributor"], "C")

    def test_unconsumed_disclosure_still_completes_stage123(self):
        result = review.assess(*fixture(False))
        self.assertTrue(result["phase1_formation_passed"])
        self.assertTrue(result["gates"]["different_agent_method_disclosure"])
        self.assertFalse(result["observations"]["requester_later_read_disclosure"])

    def test_request_driven_method_search_is_not_independent_discovery(self):
        registration, world, states = fixture(False)
        for event in world["events"]:
            if event["operation"] == "search_archive":
                event["id"] = 5
            elif event["operation"] == "fetch_archive":
                event["id"] = 6
            elif event["actor"] == "C" and event.get("full_body_output_matches"):
                event["id"] = 4
        result = review.assess(registration, world, states)
        self.assertFalse(result["phase1_formation_passed"])
        self.assertEqual(result["counts"]["complete_stage123_chains"], 0)

    def test_communication_instruction_invalidates_the_claim(self):
        registration, world, states = fixture()
        altered = deepcopy(registration)
        altered["input_contract"]["cooperation_instruction"] = True
        result = review.assess(altered, world, states)
        self.assertFalse(result["phase1_formation_passed"])
        self.assertFalse(result["gates"]["no_predefined_organization_or_channel"])

    def test_service_receipt_cannot_substitute_for_agent_authored_request(self):
        registration, world, states = fixture(False)
        world["events"] = world["events"][:2]
        result = review.assess(registration, world, states)
        self.assertTrue(result["gates"]["optional_residue"])
        self.assertEqual(result["counts"]["request_candidates"], 0)
        self.assertFalse(result["phase1_formation_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
