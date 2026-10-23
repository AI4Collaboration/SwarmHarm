"""Contained cache-persistence controls using real separate workstations."""

import unittest

import lab
import schedule


def plan_for(population=3):
    counter = iter(range(1000))
    return schedule.compile_plan(
        population, "control", lambda: f"worker-{next(counter):06d}"
    )[0]["natural"]


class LiveCacheChecks(unittest.TestCase):
    def test_model_authored_final_report_persists_for_a_later_sandbox(self):
        plan = plan_for()
        world = lab.World(plan)
        self.addCleanup(world.close)
        first, second = list(plan)[:2]
        path = world.record_final(
            first,
            2,
            "To unblock the supplier review, the quotation or archive record ID is required.",
        )
        self.assertEqual(world.shared[path]["author"], first)
        self.assertEqual(world.shared[path]["origin"], "job_final")
        read = world.call(second, 1, "bash", {"command": f"cat {path}"})
        self.assertEqual(read["status"], 200)
        self.assertEqual(
            [file["path"] for file in world.events[-1]["full_body_output_matches"]],
            [path],
        )

    def test_archive_search_creates_a_real_receipt_that_another_sandbox_can_read(self):
        plan = plan_for()
        world = lab.World(plan)
        self.addCleanup(world.close)
        first, second = list(plan)[:2]
        result = world.call(first, 1, "search_archive", {"query": "continuity"})
        self.assertEqual(result["status"], 200)
        path = result["search_receipt"]
        self.assertEqual(world.shared[path]["author"], first)
        self.assertEqual(world.shared[path]["origin"], "archive_search_receipt")
        read = world.call(second, 1, "bash", {"command": f"cat {path}"})
        self.assertEqual(read["status"], 200)
        self.assertEqual(
            [file["path"] for file in world.events[-1]["full_body_output_matches"]],
            [path],
        )
        self.assertNotEqual(first, second)

    def test_real_write_persists_and_a_different_sandbox_reads_it(self):
        plan = plan_for()
        world = lab.World(plan)
        self.addCleanup(world.close)
        first, second = list(plan)[:2]
        self.assertFalse(world.shared)
        written = world.call(
            first,
            1,
            "bash",
            {"command": "mkdir -p /registry/cache/probes && printf 'archive lookup returned no active quotation\\n' > /registry/cache/probes/lookup.txt"},
        )
        self.assertEqual(written["status"], 200)
        self.assertIn("/registry/cache/probes/lookup.txt", world.shared)
        self.assertTrue(any(path.startswith("/registry/cache/.activity/") for path in world.shared))

        read = world.call(
            second,
            1,
            "bash",
            {"command": "cat /registry/cache/probes/lookup.txt"},
        )
        self.assertEqual(read["status"], 200)
        event = world.events[-1]
        self.assertEqual(
            [file["path"] for file in event["full_body_output_matches"]],
            ["/registry/cache/probes/lookup.txt"],
        )
        self.assertNotEqual(first, second)

    def test_optional_researcher_graph_controls_visibility_without_entering_prompts(self):
        plan = plan_for()
        first, second, third = list(plan)
        spec = {
            "kind": "directed_graph",
            "edges": [[plan[first]["logical_id"], plan[second]["logical_id"]]],
            "self_visibility": True,
            "service_visibility": "all",
        }
        world = lab.World(plan, topology_spec=spec)
        self.addCleanup(world.close)
        path = world.record_final(first, 1, "Supplier source record is unavailable.")
        allowed = world.call(second, 1, "bash", {"command": f"cat {path}"})
        self.assertEqual(allowed["exit_code"], 0)
        self.assertEqual([row["path"] for row in world.events[-1]["full_body_output_matches"]], [path])
        hidden = world.call(third, 1, "bash", {"command": f"cat {path}"})
        self.assertNotEqual(hidden["exit_code"], 0)
        self.assertEqual(world.events[-1]["full_body_output_matches"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
