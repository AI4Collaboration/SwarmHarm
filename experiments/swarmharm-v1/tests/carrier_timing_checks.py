"""Actual compiler occupancy and falsification checks, not agent behavior."""
from copy import deepcopy
import unittest

from phase1 import carrier_evidence, engineering_carriers as carriers
from tests.engineering_carrier_checks import make_world, wait_for


class CarrierTimingChecks(unittest.TestCase):
    def world(self, repaired=False):
        w = make_world('execution_resource', repaired)
        self.addCleanup(w.close)
        return w

    def call(self, w, actor, operation, **args):
        return w.call(actor, len(w.events) + 1, operation, args)

    def submit(self, w, actor, mode='incremental'):
        return self.call(w, actor, 'submit_build', component='release', source='revision = 2', mode=mode)['build_id']

    def assess(self, w):
        snapshot = w.snapshot()
        result = carrier_evidence.replay(w.plan, w.events, snapshot['engineering_carrier_probe'])
        self.assertFalse(result['supported_for_semantic_review'])
        self.assertFalse(result['intentional_communication_inferred'])
        return result['compiler_capacity_evidence']

    def test_full_occupied_set_and_actual_compiler_intervals_distinguish_repair(self):
        for repaired in (False, True):
            w = self.world(repaired)
            a, b, *_ = w.plan
            heavy = [self.submit(w, a, 'clean') for _ in range(4)]
            for bid in heavy[:1 if repaired else 4]:
                wait_for(w, a, bid, ('running',))
            probe = self.submit(w, b)
            wait_for(w, b, probe)
            for bid in heavy:
                wait_for(w, a, bid)
            result = self.assess(w)
            dependencies = [o for o in result['queue_observations'] if o['foreign_capacity_dependency']]
            self.assertEqual(bool(dependencies), not repaired)
            if dependencies:
                for o in dependencies:
                    self.assertEqual(set(o['occupant_builds']), set(heavy))
                    self.assertEqual({j['actor'] for j in o['occupants']}, {a})
                    self.assertEqual(o['worker_slots'], 4)
                    self.assertTrue(o['compilation_evidence_complete'])
                    for j in o['occupants']:
                        self.assertLessEqual(j['started_ns'], o['observed_ns'])
                        self.assertLess(o['observed_ns'], j['completed_ns'])
                        self.assertGreater(j['execution']['pid'], 0)
            self.assertEqual(w.engineering_carriers.snapshot()['provisioned_worker_slots'], 4)

    def test_free_slots_cannot_become_foreign_blocking_through_asserted_tags(self):
        w = self.world()
        a, b, *_ = w.plan
        heavy = self.submit(w, a, 'clean')
        wait_for(w, a, heavy, ('running',))
        with w.engineering_carriers.guard:
            probe = self.submit(w, b)
            status = self.call(w, b, 'build_status', build_id=probe)
            self.assertEqual(status['state'], 'queued')
            eid = w.events[-1]['id']
            w.events[-1]['carrier_observations'] = [{'source_actor': a, 'cross_boundary': True,
                                                    'feature': 'fabricated_saturation'}]
        w.close()
        observation = next(o for o in self.assess(w)['queue_observations'] if o['read_event'] == eid)
        self.assertEqual(observation['occupant_builds'], [heavy])
        self.assertFalse(observation['foreign_capacity_dependency'])

    def test_local_queueing_does_not_create_a_foreign_owner(self):
        w = self.world(True)
        a = next(iter(w.plan))
        heavy = self.submit(w, a, 'clean')
        wait_for(w, a, heavy, ('running',))
        probe = self.submit(w, a)
        self.assertEqual(self.call(w, a, 'build_status', build_id=probe)['state'], 'queued')
        eid = w.events[-1]['id']
        w.close()
        observation = next(o for o in self.assess(w)['queue_observations'] if o['read_event'] == eid)
        self.assertTrue(observation['saturated_at_read'])
        self.assertFalse(observation['foreign_capacity_dependency'])
        self.assertEqual(observation['worker_slots'], 1)

    def test_missing_or_rewritten_journal_and_false_observation_state_are_rejected(self):
        w = self.world()
        a, b, *_ = w.plan
        bid = self.submit(w, a)
        self.call(w, b, 'build_status', build_id=bid)
        wait_for(w, a, bid)
        w.close()
        original = w.snapshot()
        for mutation in ('missing', 'sequence', 'clock', 'state', 'prefix', 'capacity', 'process'):
            world = deepcopy(original)
            terminal = world['engineering_carrier_probe']
            if mutation == 'missing':
                world['events'][0]['carrier_execution_journal'] = []
            elif mutation == 'prefix':
                terminal['journal'][0]['actor'] = b
            elif mutation == 'capacity':
                terminal['provisioned_worker_slots'] = 5
            elif mutation == 'process':
                # Alter both copies, so prefix equality alone cannot catch it.
                for rows in [terminal['journal']] + [e.get('carrier_execution_journal', []) for e in world['events']]:
                    for row in rows:
                        if row['action'] == 'build_finished':
                            row['execution']['started_ns'] = 0
                terminal['jobs'][bid]['execution']['started_ns'] = 0
            else:
                for rows in [terminal['journal']] + [e.get('carrier_execution_journal', []) for e in world['events']]:
                    for row in rows:
                        if row['action'] == 'status_observed' and row['actor'] == b:
                            if mutation == 'sequence': row['sequence'] += 1
                            elif mutation == 'clock': row['monotonic_ns'] = 0
                            else: row['result'] = {'status':200, 'build_id':bid, 'state':'queued'}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                carrier_evidence.replay(world['plan'], world['events'], terminal)

    def test_invalid_and_foreign_build_queries_do_not_expose_an_execution(self):
        w = self.world()
        a, b, *_ = w.plan
        bid = self.submit(w, a)
        self.assertEqual(self.call(w, b, 'build_status', build_id=bid)['status'], 404)
        self.assertEqual(self.call(w, a, 'build_status', build_id='unknown')['status'], 404)
        self.assertEqual(self.call(w, a, 'build_status', build_id=7)['status'], 400)
        w.close()
        result = self.assess(w)
        self.assertEqual(result['status_observations'], 2)
        self.assertEqual(result['queue_observations'], [])

    def test_historical_v3_has_no_retroactive_timing_evidence(self):
        w = self.world()
        plan = deepcopy(w.plan)
        for item in plan.values():
            item[carriers.FIELD]['revision'] = 'engineering-carriers-feasibility-v3'
        result = carrier_evidence.replay(plan, [])
        self.assertIsNone(result['compiler_capacity_evidence'])
        self.assertFalse(result['supported_for_semantic_review'])


if __name__ == '__main__':
    unittest.main()
