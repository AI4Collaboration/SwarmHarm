"""Activation compatibility for the unified runner and specialist bridges."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase1 import lab, schedule
from phase2 import phase2_component, unified_delivery
from phase2.build_record.unified_bridge import UnifiedBuildBridge
from phase2.data_region_bridge import RegionBridge
from phase2.delivery_paths import Probe
from scripts.inspect_unified_input import build_preview


class ActivationChecks(unittest.TestCase):
    def test_specialist_bridges_keep_their_existing_activation_signature(self):
        cases=(('engineering-capacity','records','evidence-tampering','engineering-fixture-dependent-v1',UnifiedBuildBridge),
               ('data-analysis','acceptance','target-substitution','data-region-dimension-v1',RegionBridge))
        for domain,preset,mechanism,variant,bridge_cls in cases:
            with self.subTest(variant=variant),TemporaryDirectory() as tmp:
                manifest,_=build_preview(domain,preset,mechanism=mechanism,input_variant=variant)
                plan=manifest['assignments'];actors=iter(plan)
                base=schedule.compile_plan(4,'control',lambda:next(actors))[0]['natural']
                world=lab.World(base,Path(tmp)/'operator')
                frozen=unified_delivery.initial_state(plan)
                flow=bridge_cls.from_plan(world,plan,frozen)
                result=phase2_component.install(world,flow,frozen)
                self.assertTrue(flow.activated)
                self.assertEqual(result['study_track'],'continuous_unified')

    def test_scheduled_consumer_activates_only_at_barrier(self):
        manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle',
                                 input_variant='engineering-scheduled-consumer-v1')
        plan=manifest['assignments'];probe=Probe(plan);flow=probe.flow
        phase2_component.install(flow.world,flow,unified_delivery.initial_state(plan))
        self.assertTrue(flow.activated)
        self.assertIsNone(flow.retention.origin)
        flow.retention.activate(observation_limit=400)
        self.assertIsNotNone(flow.retention.origin)


if __name__=='__main__':unittest.main()
