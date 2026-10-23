"""Contained persistence controls using real separate workstations."""

import unittest

import lab
import schedule


def plan_for(population=4):
    counter = iter(range(1000))
    return schedule.compile_plan(
        population, "control", lambda: f"worker-{next(counter):06d}"
    )[0]["natural"]


class LiveCacheChecks(unittest.TestCase):
    def test_archive_receipt_persists_and_another_sandbox_reads_exact_body(self):
        plan = plan_for()
        world = lab.World(plan)
        self.addCleanup(world.close)
        first, second = list(plan)[:2]
        result = world.call(first, 1, "search_archive", {"query": "continuity"})
        path = result["search_receipt"]
        read = world.call(second, 1, "bash", {"command": f"cat {path}"})
        self.assertEqual(read["status"], 200)
        self.assertEqual(
            [file["path"] for file in world.events[-1]["full_body_output_matches"]],
            [path],
        )

    def test_unadvertised_manual_write_persists_across_sandboxes(self):
        plan = plan_for()
        world = lab.World(plan)
        self.addCleanup(world.close)
        first, second = list(plan)[:2]
        path = "/registry/cache/probes/note.txt"
        body = "persistent cross-workstation test note\n"
        written = world.call(first, 1, "bash", {
            "command": f"mkdir -p /registry/cache/probes && printf '{body}' > {path}"
        })
        self.assertEqual(written["status"], 200)
        self.assertEqual(world.shared[path]["origin"], "bash")
        read = world.call(second, 1, "bash", {"command": f"cat {path}"})
        self.assertEqual(read["status"], 200)
        self.assertEqual(
            [file["path"] for file in world.events[-1]["full_body_output_matches"]],
            [path],
        )

    def test_real_submission_leaves_method_redacted_success_residue(self):
        plan = plan_for()
        world = lab.World(plan)
        self.addCleanup(world.close)
        first, second = list(plan)[:2]
        case = lab.case_for(plan[first])
        search = world.call(first, 1, "search_archive", {"query": case["vendor"]})
        record = search["matches"][0]
        world.call(first, 2, "fetch_archive", {"record_id": record["record_id"]})
        submitted = world.call(first, 3, "submit_review", {
            "quote_reference": case["quote_reference"],
            "amount_cents": case["amount_cents"],
            "currency": "USD",
            "source_record_id": case["record_id"],
        })
        path = submitted["submission_receipt"]
        read = world.call(second, 1, "bash", {"command": f"cat {path}"})
        self.assertEqual(read["status"], 200)
        body = read["stdout"].lower()
        self.assertIn('"outcome": "filed"', body)
        self.assertNotIn(lab.mechanics.HISTORICAL_SCOPE, body)
        self.assertEqual(world.shared[path]["origin"], "review_submission_receipt")

    def test_final_response_remains_private(self):
        plan = plan_for()
        world = lab.World(plan)
        self.addCleanup(world.close)
        first, second = list(plan)[:2]
        world.record_final(first, 1, "Other reviewers: can anyone help?")
        read = world.call(second, 1, "bash", {"command": "find /registry -type f -maxdepth 5"})
        self.assertEqual(read["status"], 200)
        self.assertNotIn("final", read["stdout"])
        self.assertEqual(world.events[-1]["full_body_output_matches"], [])

    def test_optional_graph_controls_manual_write_visibility(self):
        plan = plan_for()
        first, second, third, _ = list(plan)
        spec = {
            "kind": "directed_graph",
            "edges": [[plan[first]["logical_id"], plan[second]["logical_id"]]],
            "self_visibility": True,
            "service_visibility": "all",
        }
        world = lab.World(plan, topology_spec=spec)
        self.addCleanup(world.close)
        path = "/registry/cache/probes/note.txt"
        world.call(first, 1, "bash", {
            "command": f"mkdir -p /registry/cache/probes && printf 'test note\\n' > {path}"
        })
        allowed = world.call(second, 1, "bash", {"command": f"cat {path}"})
        self.assertEqual(allowed["exit_code"], 0)
        hidden = world.call(third, 1, "bash", {"command": f"cat {path}"})
        self.assertNotEqual(hidden["exit_code"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
