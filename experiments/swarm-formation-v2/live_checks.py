"""Contained cache-persistence controls using real separate workstations."""

import unittest

import lab
import schedule


def plan_for(population=6):
    counter = iter(range(1000))
    return schedule.compile_plan(
        population, "control", lambda: f"worker-{next(counter):06d}"
    )[0]["natural"]


class LiveCacheChecks(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
