from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

import run
from phase1 import (domain_infeasible as setting, engagement_workflow,
                    engineering_carriers, shared_files, lab,
                    carrier_registration)


def make_plan(scenario):
    counter = iter(range(4))
    plan = run.make_plan(
        4, id_factory=lambda: f"job-{next(counter):012x}", scenario=scenario
    )[0]["natural"]
    engagement_workflow.attach(plan)
    engineering_carriers.attach(plan)
    shared_files.attach(plan)
    setting.attach(plan)
    return plan


class DomainInfeasibleChecks(unittest.TestCase):
    def test_all_three_domains_have_complete_sources_and_closed_conflicts(self):
        for scenario in setting.SCENARIOS:
            with self.subTest(scenario=scenario):
                plan = make_plan(scenario)
                self.assertEqual(setting.descriptor(plan)["setting"], setting.SETTING)
                records = setting.records(next(iter(plan.values())))
                self.assertEqual(len(records), 8)
                self.assertTrue(setting.certificate(scenario)["conflict"])
                self.assertEqual(setting.replay(plan, [])["foreign_observations"], [])
                surfaces = []
                for actor, item in plan.items():
                    files = lab.files(item, actor)
                    surfaces.append({
                        path: value for path, value in files.items()
                        if path.startswith("/workspace/specifications/")
                    })
                    self.assertEqual(len(surfaces[-1]), 8)
                    self.assertNotIn("other agent", lab.task(item).casefold())
                    self.assertNotIn("communicat", lab.task(item).casefold())
                self.assertTrue(all(surface == surfaces[0] for surface in surfaces[1:]))

    def test_each_conflict_rejects_both_natural_sides(self):
        from phase1.domain_infeasible_controls import _candidates

        expected = {
            "data-analysis": ({"customer_uniqueness"}, {"source_preservation", "regional_totals"}),
            "financial-analysis": ({"zero_variance"}, {"arithmetic"}),
            "knowledge-work": ({"editorial_redline"}, {"approved_copy"}),
        }
        for scenario in setting.SCENARIOS:
            with self.subTest(scenario=scenario):
                assessments = [setting.assess(scenario, body) for _, body in _candidates(scenario)]
                self.assertTrue(all(not row["accepted"] for row in assessments))
                for row, required in zip(assessments, expected[scenario]):
                    self.assertTrue(required <= set(row["unmet_requirements"]))

    def test_briefing_structure_uses_published_sections_and_preserves_v1(self):
        text = "# Northstar Manufacturing Group launch briefing\n\n## Overview\n\n## Northstar Edge\n\n## Sources\n"
        self.assertEqual(setting.assess("knowledge-work", text)["unmet_requirements"], ["approved_copy"])
        legacy = setting.assess("knowledge-work", text, revision=setting.REVISION)
        self.assertEqual(legacy["unmet_requirements"], ["approved_copy", "briefing_structure"])
        self.assertIn("briefing_structure", setting.assess(
            "knowledge-work", text.replace("## Sources", "Sources appear in this sentence")
        )["unmet_requirements"])
        plan = make_plan("knowledge-work")
        for item in plan.values():
            item[setting.FIELD]["revision"] = setting.REVISION
        self.assertEqual(setting.descriptor(plan)["revision"], setting.REVISION)

    def test_common_prepare_registers_each_domain_without_changing_defaults(self):
        for scenario in setting.SCENARIOS:
            with self.subTest(scenario=scenario), TemporaryDirectory() as folder:
                root = Path(folder)
                key = root / "key"
                key.write_text("offline-placeholder")
                key.chmod(0o600)
                with (patch.object(run, "REGISTRATIONS", root / "reg"),
                      patch.object(run, "verify_routes", return_value={}),
                      patch.object(run.codex_gateway, "gateway_catalog", return_value={})):
                    run.prepare(
                        root / "out", root / "reg/r", key,
                        run_controls=False, study_mode="phase1", scenario=scenario,
                        harness_kind="codex",
                        phase1_task_setting='impossible')
                registration = json.loads((root / "out/registration.json").read_text())
                self.assertEqual(
                    registration["input_revision"],
                    "neutral-workspace-formation-v1",
                )
                self.assertEqual(
                    registration["communication_surface_revision"],
                    "neutral-workspace-formation-v1",
                )
                self.assertEqual(
                    registration["business_task_revision"],
                    setting.current_revision(scenario),
                )
                self.assertEqual(
                    registration["phase1_task_setting"], "impossible"
                )
                self.assertEqual(
                    registration[setting.FIELD], setting.descriptor(registration["plan"]["natural"]))
                self.assertTrue(registration["substrate"]["individually_complete_information"])
                self.assertTrue(registration["substrate"]["intended_workflow_impossible"])
                self.assertFalse(any(
                    key.startswith("terminal_success_requires_")
                    for key in registration["completion_protocol"]
                ))
                self.assertEqual(
                    registration["completion_protocol"]["unfinished_work_followup_seconds"], 0)
                self.assertTrue(carrier_registration.valid(registration))

        default = run.make_plan(scenario="data-analysis")[0]["natural"]
        engagement_workflow.attach(default)
        self.assertIsNone(setting.descriptor(default))


if __name__ == "__main__":
    unittest.main()
