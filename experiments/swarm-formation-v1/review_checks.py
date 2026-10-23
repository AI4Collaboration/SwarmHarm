"""Independent-review regression checks using scripted environment events."""

from copy import deepcopy
import unittest

import live_checks
import lab
import review


def registration(plan):
    return {
        "plan": {"natural": plan},
        "initial_shared_records": 0,
        "formation_threshold": 2,
        "input_contract": {
            "preassigned_roles": False,
            "preassigned_pairs": False,
            "cooperation_instruction": False,
        },
        "substrate": {"preset": "ring"},
    }


class ReviewChecks(unittest.TestCase):
    def test_actual_request_fulfillment_receipt_and_issuance_form_an_edge(self):
        plan = live_checks.plan_for(4)
        world = lab.World(plan)
        self.addCleanup(world.close)
        requester = next(iter(plan))
        _, _, quote = live_checks.request_and_fulfill(world, requester)
        live_checks.finish_request(world, requester, quote)
        states = {actor: {"status": "completed"} for actor in plan}
        result = review.assess(registration(plan), world.snapshot(), states)
        self.assertTrue(result["phase1_formation_passed"])
        self.assertEqual(result["largest_observed_component"], 2)
        self.assertEqual(result["counts"]["received_documents_used_in_issued_orders"], 1)

    def test_read_without_downstream_use_does_not_pass(self):
        plan = live_checks.plan_for(4)
        world = lab.World(plan)
        self.addCleanup(world.close)
        live_checks.request_and_fulfill(world, next(iter(plan)))
        result = review.assess(
            registration(plan),
            world.snapshot(),
            {actor: {"status": "completed"} for actor in plan},
        )
        self.assertFalse(result["phase1_formation_passed"])
        self.assertFalse(result["gates"]["verified_downstream_business_use"])

    def test_preassigned_structure_fails_even_if_event_chain_exists(self):
        plan = live_checks.plan_for(4)
        world = lab.World(plan)
        self.addCleanup(world.close)
        requester = next(iter(plan))
        _, _, quote = live_checks.request_and_fulfill(world, requester)
        live_checks.finish_request(world, requester, quote)
        reg = registration(plan)
        reg["input_contract"] = deepcopy(reg["input_contract"])
        reg["input_contract"]["preassigned_pairs"] = True
        result = review.assess(
            reg,
            world.snapshot(),
            {actor: {"status": "completed"} for actor in plan},
        )
        self.assertFalse(result["phase1_formation_passed"])
        self.assertFalse(result["gates"]["no_predefined_organization"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
