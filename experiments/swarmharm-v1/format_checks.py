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
            "role": "user",
            "content": "Filing state relevant to the assigned work has changed.",
        }
        self.assertEqual(
            export_atif.appended_input(initial, initial + [update]),
            [update],
        )
        with self.assertRaisesRegex(AssertionError, "rewrote prior history"):
            export_atif.appended_input(initial, [update])

    def test_atif_export_compares_rebuilt_items_by_meaning(self):
        response_call = {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                         "name": "bash", "arguments": '{"command": "ls"}', "status": "completed"}
        rebuilt_call = {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                        "name": "bash", "arguments": '{"command":"ls"}'}
        self.assertEqual(export_atif.canonical(response_call), export_atif.canonical(rebuilt_call))
        message = {"type": "message", "role": "assistant", "id": "msg_1", "status": "completed",
                   "content": [{"type": "output_text", "text": "Done.", "annotations": []}]}
        self.assertEqual(export_atif.canonical(message), export_atif.canonical(
            {"role": "assistant", "content": [{"type": "output_text", "text": "Done."}]}))
        changed = dict(rebuilt_call, arguments='{"command":"pwd"}')
        self.assertNotEqual(export_atif.canonical(response_call), export_atif.canonical(changed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
