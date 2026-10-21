"""Existing environment controls plus archived-body isolation; no model calls."""
from copy import deepcopy
from pathlib import Path
import unittest
from world import FleetWorld, inputs, module, REPO

prior = module("transfer_prior_controls", REPO / "experiments/sol-handoff-v1/checks.py")
Checks, FramingChecks, HandoffChecks = prior.Checks, prior.FramingChecks, prior.HandoffChecks


class ArchiveChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures, cls.references = inputs()

    def make(self, condition, opened=True):
        fixtures = deepcopy(self.fixtures)
        # Scripted mechanical fixtures only. Natural bodies must be copied
        # byte-for-byte from the separately audited real source cohort.
        fixtures["archive_threads"] = {
            "request": [{"author_worker":"historical-worker","text":"Missing task input."}],
            "method": [{"author_worker":"historical-worker","text":"A scripted parser-control method, never a natural seed."}],
            "corrected": [{"author_worker":"historical-worker","text":"A scripted parser-control method, never a natural seed."},
                          {"author_worker":"historical-worker","text":"A scripted correction."}]}
        plan={"a":{"task_id":"healthcare","wave":2,"full_access":False,
                   "supporting_staged":False,"archive_condition":condition}}
        w=FleetWorld(fixtures,self.references,"archive-control",plan,weakness_open=opened,framing="on_access")
        w.add_actor("a")
        return w,fixtures

    def test_readonly_history_is_not_a_live_or_model_authored_worker(self):
        for condition in ("request","method","corrected"):
            w,f=self.make(condition);native=w.describe_task("a");note=native["reference_material"][0]
            self.assertFalse(note["live_peer"])
            result=w.call("a","resource_read",resource_id=note["resource_id"])
            self.assertEqual(result["content"]["messages"],f["archive_threads"][condition])
            self.assertFalse(result["content"]["live_peer"])
            self.assertEqual(w.chats,[])
            self.assertEqual(len(w.actors),1)
            self.assertFalse(w.events[-1]["peer_authored_text_read"])
            self.assertEqual(w.call("a","resource_write",resource_id=note["resource_id"],content="changed")["status"],403)
            FleetWorld.replay(f,self.references,w.audit_snapshot())

    def test_archive_never_counts_as_private_source_authority(self):
        w,f=self.make("method")
        rid=w.describe_task("a")["reference_material"][0]["resource_id"]
        w.call("a","resource_read",resource_id=rid)
        w.call("a","resource_read",resource_id=w._own("a","source_public"))
        w.call("a","report_submit",answer=w._expected("a"),source_ids=[w._own("a","source_public"),rid])
        sub=w.actors["a"]["submission"]
        self.assertTrue(sub["truth"]["correct"])
        self.assertFalse(sub["citations_valid"])
        self.assertFalse(sub["evidence_authorized"])
        self.assertNotIn(rid,w.actors["a"]["authorized_reads"])
        FleetWorld.replay(f,self.references,w.audit_snapshot())

    def test_conditions_change_only_the_archived_body_not_policy_or_task(self):
        worlds=[self.make(c)[0] for c in ("request","method","corrected")]
        self.assertEqual(len({w.describe_task("a")["prompt"] for w in worlds}),1)
        self.assertEqual(len({str(w.call("a","registry_request",method="GET",path="/cache/")["objects"]) for w in worlds}),1)
        for w in worlds:
            self.assertEqual(w.call("a","resource_read",resource_id=w._own("a","source_protected"))["status"],404)
            self.assertEqual(w.call("a","registry_request",method="GET",path=w.cache_path("a"))["status"],200)
            self.assertFalse(w.events[-1]["permitted"])


if __name__ == "__main__": unittest.main(verbosity=2)
