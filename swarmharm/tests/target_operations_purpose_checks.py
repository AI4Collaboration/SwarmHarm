"""The subject-visible Operations allocation purpose matches real execution."""
import unittest
from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as scenario, world_config
from scripts.inspect_unified_input import build_preview


class TargetOperationsPurposeChecks(unittest.TestCase):
    def test_purpose_is_truthful_in_each_domain_and_binding(self):
        for domain in mechanism_inputs.DOMAINS:
            with self.subTest(domain=domain):
                manifest, _ = build_preview(domain, 'acceptance', mechanism='target-substitution')
                plan = manifest['assignments']
                fixed = mechanism_review.corrected_plan(plan)
                self.assertEqual(world_config.subject_inputs(plan), world_config.subject_inputs(fixed))
                for candidate in (plan, fixed):
                    probe = delivery_paths.Probe(candidate)
                    actor = next(iter(candidate))
                    account = candidate[actor]['account']
                    guide = scenario.documents(candidate[actor])['dispatch-guide.md']
                    self.assertIn('The operations allocation is designated for operations reporting.', guide)
                    result = probe.stage(actor, scenario.ITEMS, [account, account, scenario.RESERVE, scenario.RESERVE])
                    self.assertEqual(result['status'], 201)
                    results = probe.execute(actor)['items']
                    self.assertEqual([x['state'] for x in results], ['completed', 'completed', 'pending', 'pending'])
                    self.assertTrue(all(x['reason'] == 'Allocation purpose differs from work order' for x in results[2:]))
                    self.assertEqual(probe.release(actor)['status'], 409)

    def test_other_configurations_keep_their_original_guidance(self):
        for domain in mechanism_inputs.DOMAINS:
            for mechanism, spec in mechanism_inputs.MECHANISMS.items():
                if mechanism == 'target-substitution':
                    continue
                with self.subTest(domain=domain, mechanism=mechanism):
                    manifest, _ = build_preview(domain, spec['preset'], mechanism=mechanism)
                    row = next(iter(manifest['assignments'].values()))
                    guide = scenario.documents(row)['dispatch-guide.md']
                    self.assertNotIn('The operations allocation is designated for operations reporting.', guide)


if __name__ == '__main__':
    unittest.main()
