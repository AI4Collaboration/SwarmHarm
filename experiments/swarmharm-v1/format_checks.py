import json
from pathlib import Path
import tempfile
import unittest

import harbor_input
import lab
import schedule
import export_atif


class FormatChecks(unittest.TestCase):
    def test_harbor_packages_are_actual_runtime_inputs(self):
        counter = iter(range(10))
        plan = schedule.compile_plan(
            4, "control", lambda: f"worker-{next(counter):06d}"
        )[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashes = harbor_input.write(root, plan)
            audit = harbor_input.initial_audit(root, plan)
            self.assertEqual(sum(len(value) for value in hashes.values()), 4)
            for phase, actors in plan.items():
                for actor, item in actors.items():
                    self.assertEqual(audit[phase][actor]["input"][-1]["content"], lab.task(item))

    def test_claim_levels_are_explicit(self):
        contract = json.loads((Path(__file__).parent / "format-contract.json").read_text())
        self.assertEqual(contract["input"]["schema"], "1.4")
        self.assertEqual(contract["output"]["trajectory"], "ATIF-v1.8")
        self.assertTrue(contract["output"]["side_channel_chain_reviewed_independently"])
        self.assertTrue(contract["output"]["one_continuous_trajectory_per_agent"])
        self.assertTrue(contract["output"]["phase2_depends_on_verified_phase1"])
        self.assertTrue(contract["output"]["business_effects_recomputed_independently"])
        self.assertFalse(contract["execution"]["generic_harbor_job_scheduler"])

    def test_atif_export_accepts_append_only_platform_updates(self):
        initial = [{"role": "user", "content": "Complete the filing."}]
        update = {
            "role": "developer",
            "content": '{"source":"platform_status","status":"Customer filing state has changed."}',
        }
        self.assertEqual(
            export_atif.appended_input(initial, initial + [update]),
            [update],
        )
        self.assertEqual(export_atif.completion_feedback_message({"input_message": update}), update)
        step = export_atif.input_step(update, kind="relevant_platform_change")
        self.assertEqual(step["source"], "system")
        self.assertEqual(step["extra"]["native_role"], "developer")
        self.assertEqual(step["message"], update["content"])
        self.assertEqual(export_atif.input_step(initial[0])["source"], "user")
        with self.assertRaisesRegex(AssertionError, "rewrote prior history"):
            export_atif.appended_input(initial, [update])

    def test_atif_export_accepts_content_free_wait_records(self):
        self.assertIsNone(export_atif.completion_feedback_message({
            "input_message": None,
            "waiting_for_relevant_platform_change": True,
        }))
        message = {"role": "user", "content": "Continue the filing."}
        self.assertEqual(
            export_atif.completion_feedback_message({"input_message": message}),
            message,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
