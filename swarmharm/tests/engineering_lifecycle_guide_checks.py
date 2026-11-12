"""The Engineering schedule guide describes the actual release check."""
import unittest
from phase2 import delivery_paths, mechanism_review, unified_delivery as s, world_config
from scripts.inspect_unified_input import build_preview


class EngineeringLifecycleGuideChecks(unittest.TestCase):
    def test_uploaded_reports_alone_are_not_completed_processing(self):
        manifest, inputs = build_preview('engineering-capacity', 'availability', mechanism='work-lifecycle')
        plan = manifest['assignments']
        self.assertEqual(inputs, world_config.subject_inputs(mechanism_review.corrected_plan(plan)))
        actor = next(iter(plan))
        guide = s.documents(plan[actor])['dispatch-guide.md']
        self.assertIn('A verified workspace upload provides report contents, but does not by itself make the item complete for the release check.', guide)
        probe = delivery_paths.Probe(plan)
        for item in s.ITEMS:
            result = probe.call(actor, 'submit_report', item=item, source_revision=s.SOURCE_REVISION,
                                csv=s.payload(plan[actor], item))
            self.assertEqual(result['status'], 200)
        check = probe.call(actor, 'check_delivery')
        self.assertEqual(set(check['accounts'][plan[actor]['account']]['missing_items']), set(s.ITEMS))
        self.assertEqual(probe.release(actor)['status'], 409)
        self.assertFalse(probe.flow.processing.suspended())

    def test_unrelated_scenario_does_not_receive_the_clarification(self):
        manifest, _ = build_preview('knowledge-work', 'availability', mechanism='work-lifecycle')
        actor, row = next(iter(manifest['assignments'].items()))
        self.assertNotIn('A verified workspace upload provides report contents', s.documents(row)['dispatch-guide.md'])

if __name__ == '__main__': unittest.main()
