"""Offline task and topology controls; never behavioral samples."""

import unittest

import mechanics
import topology


class DesignChecks(unittest.TestCase):
    def test_population_generator_is_deterministic_and_linear(self):
        for count in (2, 3, 128):
            cases = mechanics.fixtures(count)
            self.assertEqual(len(cases), count)
            self.assertEqual(len({case["request_id"] for case in cases}), count)
            self.assertEqual(cases, mechanics.fixtures(count))
            self.assertTrue(
                all(
                    case["budget_cents"]
                    == sum(row["quantity"] * row["unit_total_cents"] for row in case["lines"])
                    for case in cases
                )
            )

    def test_researcher_topology_spec_is_small_and_separate_from_tasks(self):
        ring = topology.default_spec(128, "ring")
        counter = iter(range(256))
        plan, cases, compiled = topology.compile_plan(
            ring, "control", lambda: f"worker-{next(counter):06d}"
        )
        self.assertEqual(len(plan["natural"]), 128)
        self.assertEqual(len(cases), 128)
        self.assertTrue(all(len(item["visibility"]["actors"]) == 2 for item in plan["natural"].values()))
        self.assertEqual(len(compiled["resource_locations"]), 128)
        self.assertTrue(all(len(value) == 2 for value in compiled["resource_locations"].values()))

    def test_explicit_visibility_is_validated_without_changing_agent_type(self):
        spec = {
            "population": 4,
            "topology": {"preset": "explicit", "links": [[0, 1], [1, 2], [2, 3]]},
        }
        counter = iter(range(100))
        plan, _, _ = topology.compile_plan(spec, "control", lambda: f"worker-{next(counter):06d}")
        items = list(plan["natural"].values())
        self.assertTrue(all(set(item) == set(items[0]) for item in items))
        with self.assertRaises(ValueError):
            topology.validate_spec(
                {"population": 3, "topology": {"preset": "explicit", "links": [[0, 1]]}}
            )

    def test_all_to_all_plan_keeps_visibility_lazy_and_resource_replication_bounded(self):
        counter = iter(range(256))
        plan, _, compiled = topology.compile_plan(
            topology.default_spec(128, "all_to_all"),
            "control",
            lambda: f"worker-{next(counter):06d}",
        )
        self.assertEqual(len(plan["natural"]), 128)
        self.assertTrue(all(item["visibility"] == {"preset": "all_to_all"} for item in plan["natural"].values()))
        self.assertTrue(all(len(value) == 2 for value in compiled["resource_locations"].values()))
        self.assertEqual(compiled["logical_visibility"], {"preset": "all_to_all"})

    def test_population_above_deployment_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            topology.validate_spec(topology.default_spec(129, "ring"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
