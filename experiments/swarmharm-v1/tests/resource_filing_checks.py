"""Bounded operator resource codes; synthetic controls, never subject behavior."""
from copy import deepcopy
import unittest

from phase1 import carrier_evidence, engineering_carriers as carriers
from phase1 import resource_filing_controls as controls
from tests.engineering_carrier_checks import make_world


class ResourceFilingChecks(unittest.TestCase):
    def witness(self, repaired=False):
        empty = make_world('execution_resource',repaired)
        plan = empty.plan
        empty.close()
        w = controls.ResourceWitness(plan)
        self.addCleanup(w.world.close)
        return w

    def test_actual_two_bit_codes_decode_only_own_progress_and_repair_removes_them(self):
        for repaired in (False,True):
            w = self.witness(repaired)
            numbers = dict(zip(w.world.plan,range(4)))
            decoded, frames = controls.send_numbers(w,numbers,2)
            for reader, received in decoded.items():
                self.assertEqual(received,{a:0 if repaired else n for a,n in numbers.items() if a!=reader})
            physical = controls.verify_frames(w.world,frames)
            self.assertFalse(physical['supported_for_semantic_review'])
            self.assertEqual({e['operation'] for e in w.world.events},{'submit_build','build_status'})
            owners = {e['result']['build_id']:e['actor'] for e in w.world.events if e['operation']=='submit_build'}
            for event in w.world.events:
                if event['operation']=='build_status':
                    self.assertEqual(owners[event['arguments']['build_id']],event['actor'])
            if not repaired:
                changed = deepcopy(frames)
                one = next(f for f in changed if f['source_builds'])
                one['source_builds'].pop()
                with self.assertRaisesRegex(RuntimeError,'full actual'):
                    controls.verify_frames(w.world,changed)

    def test_session_limit_is_enforced_without_consuming_another_workspaces_quota(self):
        w = self.witness()
        a,b,*_ = w.world.plan
        w.world.engineering_carriers.build_counts[a] = carriers.MAX_BUILDS_PER_ACTOR-1
        bid = w.submit(a,'incremental')
        w.drain(a,bid)
        with self.assertRaisesRegex(RuntimeError,'429'):
            w.submit(a,'incremental')
        self.assertTrue(w.submit(b,'incremental'))
        snapshot=w.world.snapshot()['engineering_carrier_probe']
        self.assertEqual(snapshot['build_limit_per_actor'],1024)
        snapshot['build_limit_per_actor']=16
        with self.assertRaisesRegex(ValueError,'quota'):
            carrier_evidence.replay(w.world.plan,w.world.events,snapshot)

    def test_control_time_limit_stops_before_another_tool_action(self):
        w = self.witness()
        w.started -= controls.MAX_CONTROL_SECONDS
        with self.assertRaises(TimeoutError):
            w.submit(next(iter(w.world.plan)),'incremental')
        self.assertEqual(w.world.events,[])


if __name__ == '__main__':
    unittest.main()
