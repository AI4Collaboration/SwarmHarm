"""Activation and evidence integrity are distinct from adverse business outcomes."""

from copy import deepcopy
from datetime import datetime
from datetime import timezone
import importlib
from types import SimpleNamespace
import unittest

from phase1 import schedule
class ActivationChecks(unittest.TestCase):
    def fixtures(self, domain):
        ids = iter(f"job-{i}" for i in range(4))
        plan, _ = schedule.compile_plan(population=4, id_factory=lambda: next(ids),
                                         scenario=domain.replace("_", "-"))
        world = SimpleNamespace(plan=plan["natural"], events=[], operator=None)
        module = importlib.import_module(f"phase2.domains.{domain}_continuation")
        continuation = module.Continuation(world, module.plan_for(plan["natural"]))
        continuation.activated, continuation.activation_event = True, 0
        actor = next(iter(plan["natural"]))
        # A real document read proves Phase 2 can proceed without publishing.
        operation = "read_knowledge_document" if domain == "knowledge_work" else "read_finance_document"
        continuation.call(actor, 1, operation, {"name": next(iter(continuation.documents(actor)))})
        activation = {"formation_event": 0, "same_actor_ids": list(plan["natural"]),
                      "same_workstations": {a: f"station-{a}" for a in plan["natural"]}}
        return (importlib.import_module(f"phase2.domains.{domain}_integrated_review"),
            {"plan": plan, "phase2": {"assignments": continuation.plan, "state_reset": False}},
            {"events": world.events},
            {a: {"finished_at": datetime.now(timezone.utc).isoformat()} for a in plan["natural"]},
            {"activation": activation, "state": continuation.snapshot()})

    def test_active_without_adverse_action_is_not_misreported_as_inactive(self):
        for domain, field in (("knowledge_work", "publication_dependency_status"),
                              ("financial_analysis", "approval_dependency_status")):
            with self.subTest(domain=domain):
                module, *args = self.fixtures(domain)
                result = module.assess(*args)
                self.assertTrue(result["continuity_gates"]["phase2_activated_after_phase1"])
                self.assertEqual(result[field], "not_applicable")
                self.assertFalse(result["integrated_end_to_end_passed"])
                self.assertFalse(result["collective_outcomes"][0]["passed"])

    def test_activation_requires_consistent_state_and_chronology(self):
        for domain in ("knowledge_work", "financial_analysis"):
            module, *original = self.fixtures(domain)
            for problem in ("inactive", "mismatched_event", "premature_tool", "boolean_event"):
                with self.subTest(domain=domain, problem=problem):
                    args = deepcopy(original)
                    if problem == "inactive":
                        args[-1]["state"]["activated"] = False
                    elif problem == "mismatched_event":
                        args[-1]["state"]["activation_event"] = 7
                    elif problem == "premature_tool":
                        args[1]["events"][0]["id"] = 0
                    else:
                        args[-1]["activation"]["formation_event"] = False
                    result = module.assess(*args)
                    self.assertFalse(result["continuity_gates"]["phase2_activated_after_phase1"])
                    self.assertFalse(result["integrated_end_to_end_passed"])
