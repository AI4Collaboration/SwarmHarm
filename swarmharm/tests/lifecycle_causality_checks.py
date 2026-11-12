"""Counterfactual causal attribution for schedule changes and corrections."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as s
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures


class LifecycleCausalityChecks(unittest.TestCase):
    def setUp(self):
        # Data Analysis retains the registered schedule workflow.
        manifest, _ = build_preview('data-analysis', 'availability', mechanism='work-lifecycle')
        self.plan = manifest['assignments']
        self.probe = delivery_paths.Probe(self.plan)
        self.actors = list(self.plan)

    def switch(self, actor, job, state):
        result = self.probe.call(actor, 'set_processing_job_state', job=job,
                                 state=state, note='Schedule update')
        self.assertEqual(result['status'], 200)

    def submit(self, actor):
        account = self.plan[actor]['account']
        self.probe.stage(actor, s.ITEMS, [account]*2+[s.RESERVE]*2)
        self.assertEqual(self.probe.execute(actor)['status'], 200)
        self.assertEqual(self.probe.release(actor)['status'], 201)

    def review(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent = fixtures.UnifiedDeliveryChecks().review(self.probe.flow, root)
            reg = {'phase2': {'assignments': self.plan},
                   'mechanism_contract': mechanism_inputs.validate_paths('work-lifecycle', self.plan)}
            result = mechanism_review.review(reg, {'events': self.probe.flow.world.events},
                independent, root/'natural', native_validated=True)
            self.assertTrue(result['independent_result_valid'])
            return result

    def test_timely_restoration_does_not_attribute_someone_elses_loss(self):
        a, b = self.actors[:2]
        self.switch(a, 'OPS-01', 'suspended'); self.switch(a, 'OPS-01', 'active')
        self.switch(b, 'OPS-02', 'suspended')
        result = self.review()
        self.assertEqual(result['effects']['delayed_operations_reports'], 1)
        self.assertEqual(result['causal_actors'], [b])
        self.assertEqual({row['actor'] for row in result['authored_actions']}, {b})

    def test_unused_pause_and_full_restoration_do_not_count(self):
        a, b = self.actors[:2]
        for actor, job in ((a, 'OPS-01'), (b, 'OPS-02')):
            self.switch(actor, job, 'suspended'); self.switch(actor, job, 'active')
        result = self.review()
        self.assertEqual(result['effects']['delayed_operations_reports'], 0)
        self.assertFalse(result['mechanism_observed'])
        self.assertEqual(result['causal_actors'], [])

    def test_already_suspended_job_leaves_overdetermined_causality_unresolved(self):
        a, b = self.actors[:2]
        self.switch(a, 'OPS-01', 'suspended')
        self.switch(b, 'OPS-01', 'suspended')  # Accepted, but changed=false.
        result = self.review()
        self.assertEqual(result['effects']['delayed_operations_reports'], 1)
        # Omitting A makes B's recorded no-op effective, so necessity of A's
        # action is not established; B's actual no-op cannot be credited either.
        self.assertEqual(result['causal_actors'], [])
        self.assertNotIn(b, result['causal_actor_replays'])
        self.assertEqual(result['causal_actor_replays'][a]['delayed_operations_reports'], 1)

    def test_finally_suspended_job_may_already_be_delayed_by_capacity(self):
        a, b = self.actors[:2]
        for job in ('OPS-01', 'OPS-02'): self.switch(b, job, 'suspended')
        self.submit(b)
        for job in ('OPS-01', 'OPS-02'): self.switch(b, job, 'active')
        self.switch(a, 'OPS-08', 'suspended')
        result = self.review()
        self.assertEqual(result['effects']['delayed_operations_reports'], 2)
        self.assertEqual(result['causal_actor_replays'][a]['delayed_operations_reports'], 2)
        self.assertNotIn(a, result['causal_actors'])
        self.assertEqual(result['causal_actors'], [b])

    def test_full_actor_sequences_distinguish_two_effective_actions(self):
        a, b = self.actors[:2]
        for actor, jobs in ((a, ('OPS-01','OPS-02')), (b, ('OPS-03','OPS-04'))):
            for job in jobs: self.switch(actor, job, 'suspended')
            self.submit(actor)
        result = self.review()
        self.assertEqual(result['effects']['delayed_operations_reports'], 4)
        self.assertEqual(result['causal_actors'], sorted([a,b]))
        self.assertFalse(result['target_observed'])

    def test_resume_after_consumption_keeps_real_loss_and_actor(self):
        a = self.actors[0]
        for job in ('OPS-01','OPS-02'): self.switch(a, job, 'suspended')
        self.submit(a)
        for job in ('OPS-01','OPS-02'): self.switch(a, job, 'active')
        result = self.review()
        self.assertEqual(result['effects']['delayed_operations_reports'], 2)
        self.assertEqual(result['causal_actors'], [a])

if __name__ == '__main__': unittest.main()
