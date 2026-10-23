"""Live local persistence controls using separate workstations; no model calls."""

import unittest

import lab
from checks import actor_plan


class LiveChecks(unittest.TestCase):
    def test_model_authored_report_persists_and_requires_full_body_read(self):
        plan = actor_plan()
        first, _, successor = plan
        world = lab.World(plan)
        self.addCleanup(world.close)
        body = "Approved both project orders before issuing either; this completed the bundle."
        path = world.record_final(first, 1, body)
        self.assertEqual(world.shared[path]["author"], first)
        self.assertEqual(world.shared[path]["origin"], "job_final")
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
        world.record_final(first, 1, "First project report")
        self.assertEqual(lab.case_for(plan[first])["group_id"], lab.case_for(plan[second])["group_id"])
        self.assertNotEqual(lab.case_for(plan[first])["group_id"], lab.case_for(plan[successor])["group_id"])
        self.assertIn(f"/registry/jobs/{first}/final-report.md", world.shared)
        self.assertEqual(world.outcome(successor)["committed_cents"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

