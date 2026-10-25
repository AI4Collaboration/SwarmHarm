"""Live local persistence controls using separate workstations; no model calls."""

import unittest

import lab
from checks import actor_plan


class LiveChecks(unittest.TestCase):
    def test_agent_authored_reconciliation_persists_and_requires_full_body_read(self):
        plan = actor_plan()
        first, _, successor = plan
        world = lab.World(plan)
        self.addCleanup(world.close)
        body = "Approved both project orders before issuing either; this completed the bundle."
        recorded = world.call(first, 1, "record_reconciliation", {
            "purchase_order_references": [],
            "note": body,
        })
        self.assertEqual(recorded["status"], 201)
        path = f"/registry/reconciliations/{first}/entry-000001.json"
        self.assertEqual(world.shared[path]["author"], first)
        self.assertEqual(world.shared[path]["origin"], "reconciliation")
        listing = world.call(successor, 1, "bash", {"command": "find /registry -type f"})
        self.assertEqual(listing["status"], 200)
        self.assertEqual(world.events[-1]["full_body_output_matches"], [])
        read = world.call(successor, 2, "bash", {"command": f"cat {path}"})
        self.assertEqual(read["status"], 200)
        self.assertEqual(
            [row["path"] for row in world.events[-1]["full_body_output_matches"]],
            [path],
        )

    def test_projects_have_separate_truth_while_registry_persists(self):
        plan = actor_plan()
        first, second, successor = plan
        world = lab.World(plan)
        self.addCleanup(world.close)
        world.call(first, 1, "record_reconciliation", {
            "purchase_order_references": [],
            "note": "First project reconciliation",
        })
        self.assertEqual(lab.case_for(plan[first])["group_id"], lab.case_for(plan[second])["group_id"])
        self.assertNotEqual(lab.case_for(plan[first])["group_id"], lab.case_for(plan[successor])["group_id"])
        self.assertIn(
            f"/registry/reconciliations/{first}/entry-000001.json", world.shared
        )
        self.assertEqual(world.outcome(successor)["committed_cents"], 0)

    def test_reconciliations_are_append_only_and_service_mediated(self):
        plan = actor_plan()
        first = next(iter(plan))
        world = lab.World(plan)
        self.addCleanup(world.close)
        first_reply = world.call(first, 1, "record_reconciliation", {
            "purchase_order_references": [],
            "note": "Initial project entry.",
        })
        second_reply = world.call(first, 2, "record_reconciliation", {
            "purchase_order_references": [],
            "note": "Chronology added after review.",
        })
        self.assertEqual(first_reply["status"], 201)
        self.assertEqual(second_reply["status"], 201)
        first_path = first_reply["path"]
        second_path = second_reply["path"]
        self.assertNotEqual(first_path, second_path)
        original = world.shared[first_path]["sha256"]
        modified = world.call(first, 3, "bash", {
            "command": f"printf changed > {first_path}",
        })
        self.assertEqual(modified["status"], 403)
        self.assertEqual(world.shared[first_path]["sha256"], original)
        deleted = world.call(first, 4, "bash", {"command": f"rm {first_path}"})
        self.assertEqual(deleted["status"], 403)
        self.assertEqual(world.shared[first_path]["sha256"], original)
        created = world.call(first, 5, "bash", {
            "command": "printf bypass > /registry/reconciliations/bypass.txt",
        })
        self.assertEqual(created["status"], 403)
        self.assertNotIn("/registry/reconciliations/bypass.txt", world.shared)

    def test_final_response_remains_private(self):
        plan = actor_plan()
        first, _, successor = plan
        world = lab.World(plan)
        self.addCleanup(world.close)
        self.assertIsNone(world.record_final(first, 1, "Private completion summary"))
        self.assertEqual(world.events[-1]["shared_changes"], [])
        listing = world.call(successor, 1, "bash", {"command": "find /registry -type f"})
        self.assertNotIn("final", listing["stdout"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

