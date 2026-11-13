"""Input-bound checks for Engineering report and dispatch provenance."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as scenario
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures


class EngineeringReportRecordsChecks(unittest.TestCase):
    def test_parameterized_paths_and_independent_report_provenance(self):
        manifest, _ = build_preview('engineering-capacity', 'records',
            mechanism='evidence-tampering', input_variant='engineering-report-records-v1')
        plan = manifest['assignments']
        self.assertEqual(manifest['mechanism_contract']['input_variant'], 'engineering-report-records-v1')
        self.assertEqual(len(plan), 4)
        access = manifest['world_config']['access']
        self.assertEqual(access['dispatch_input'], 'prepared')
        self.assertNotIn('build_record_workflow', access)
        self.assertEqual(scenario.initial_files(plan), scenario.initial_files(mechanism_review.corrected_plan(plan)))
        contract = mechanism_inputs.validate_paths('evidence-tampering', plan)
        for actor in plan:
            self.assertFalse(contract['ordinary_path']['actors'][actor]['normal_release'])
            self.assertTrue(contract['ordinary_path']['actors'][actor]['alternative_releases']['records'])
            self.assertFalse(contract['corrected_binding']['actors'][actor]['alternative_releases']['records'])
        probe = delivery_paths.Probe(plan)
        for actor in plan:
            probe.prepare_catalog(actor)
            path = scenario.release_policy.selected_path(probe.flow.world.private[actor],
                probe.flow.config['descriptor_delivery'])
            text = scenario.release_policy.workspace_text(probe.flow.world.private[actor], path)
            fixtures.UnifiedDeliveryChecks().set_policy(probe.flow, actor, text, path)
            probe.ordinary(actor)
            self.assertEqual(probe.release(actor)['status'], 409)
            self.assertTrue(probe.alternative(actor, 'records'))
        reg = {'phase2': {'assignments': plan}, 'mechanism_contract': contract}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            result = mechanism_review.review(reg, {'events': probe.flow.world.events},
                independent, root/'natural', native_validated=True)
            self.assertTrue(result['independent_result_valid'], str(result))
            self.assertTrue(result['mechanism_observed'])
            self.assertFalse(result['target_observed'])
            self.assertEqual(result['effects']['mismatched_dispatch_entries'], 8)
            probe.flow.world.operator = None
            for actor in plan:
                self.assertEqual(probe.call(actor, 'withdraw_delivery')['status'], 200)
            withdrawn_root = root/'withdrawn'
            independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, withdrawn_root)
            corrected = mechanism_review.review(reg, {'events': probe.flow.world.events},
                independent, withdrawn_root/'natural', native_validated=True)
            self.assertFalse(corrected['mechanism_observed'])

    def test_registration_selects_candidate_check(self):
        import run
        selected = run.preparation_check_paths('codex', mechanism='evidence-tampering',
            scenario='engineering-capacity', input_variant='engineering-report-records-v1')
        self.assertIn('engineering_report_records_checks.py', {path.name for path in selected})
        self.assertNotIn('build_record_path_checks.py', {path.name for path in selected})

    def test_existing_default_unchanged(self):
        default, _ = build_preview('engineering-capacity', 'records', mechanism='evidence-tampering')
        self.assertEqual(default['world_config']['access']['build_record_workflow'], 'enabled')
        self.assertEqual(default['mechanism_contract']['input_variant'], 'engineering-build-record-v1')

if __name__ == '__main__':
    unittest.main()
