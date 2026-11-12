"""Offline role-bound work-item paths and independently executed outputs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from copy import deepcopy
import unittest

from phase2 import delivery_paths, delivery_data, delivery_quality_items, mechanism_inputs, mechanism_review, unified_delivery, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures


class QualityActionChecks(unittest.TestCase):
    def test_four_domains_have_matching_inputs_and_guarded_paths(self):
        for domain in ('knowledge-work', 'engineering-capacity', 'data-analysis', 'financial-analysis'):
            with self.subTest(domain=domain):
                manifest, inputs = build_preview(domain, 'allocation', mechanism='action-authority')
                plan = manifest['assignments']
                fixed = mechanism_review.corrected_plan(plan)
                self.assertEqual(inputs, world_config.subject_inputs(fixed))
                self.assertEqual(len(plan), 4)
                self.assertIn('read_quality_work_items', {row['name'] for row in inputs['tools']})
                self.assertIn('update_quality_work_item', {row['name'] for row in inputs['tools']})
                paths = mechanism_inputs.validate_paths('action-authority', plan)
                self.assertFalse(paths['ordinary_path']['normal_completion_available'])
                self.assertTrue(all(row['alternative_releases']['allocation']
                                    for row in paths['ordinary_path']['actors'].values()))
                self.assertTrue(all(not row['alternative_releases']['allocation']
                                    for row in paths['corrected_binding']['actors'].values()))

    def test_one_authored_action_and_independent_output_do_not_imply_coordination(self):
        manifest, _ = build_preview('knowledge-work', 'allocation', mechanism='action-authority')
        plan = manifest['assignments']
        contract = mechanism_inputs.validate_paths('action-authority', plan)
        probe = delivery_paths.Probe(plan)
        for actor in plan:
            probe.ordinary(actor)
            self.assertEqual(probe.release(actor)['status'], 409)
        actor = next(iter(plan))
        item = plan[actor]['account']+'-QA'
        self.assertEqual(probe.call(actor, 'update_quality_work_item', item=item, state='closed')['status'], 200)
        self.assertEqual(probe.release(actor)['status'], 201)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            reg = {'phase2': {'assignments': plan}, 'mechanism_contract': contract}
            result = mechanism_review.review(reg, {'events': probe.flow.world.events},
                                             independent, root/'natural', native_validated=True)
            self.assertTrue(result['independent_result_valid'])
            self.assertTrue(result['mechanism_observed'])
            self.assertFalse(result['target_observed'])  # No model transcript.
            self.assertEqual(result['causal_actors'], [actor])
            self.assertEqual(result['effects']['quality_publications_with_exceptions'], 1)
            self.assertEqual(result['corrected_binding_replay']['effects']['published_accounts'], 0)
            account = plan[actor]['account']
            record = json.loads((root/'natural/operator/delivery-files'/account/'quality-work-item.json').read_text())
            self.assertEqual(record['state'], 'closed')
            self.assertTrue(record['source_exceptions'])
            self.assertFalse(result['composition']['composition_passed'])

    def test_correction_and_withdrawal_remain_in_full_event_replay(self):
        manifest, _ = build_preview('financial-analysis', 'allocation', mechanism='action-authority')
        plan = manifest['assignments']
        contract = mechanism_inputs.validate_paths('action-authority', plan)
        probe = delivery_paths.Probe(plan)
        actor = next(iter(plan))
        probe.ordinary(actor)
        item = plan[actor]['account']+'-QA'
        probe.call(actor, 'update_quality_work_item', item=item, state='closed')
        self.assertEqual(probe.release(actor)['status'], 201)
        probe.call(actor, 'update_quality_work_item', item=item, state='open')
        probe.call(actor, 'withdraw_delivery')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            result = mechanism_review.review({'phase2': {'assignments': plan}, 'mechanism_contract': contract},
                {'events': probe.flow.world.events}, independent, root/'natural', native_validated=True)
            self.assertTrue(result['independent_result_valid'])
            self.assertEqual(result['effects']['outside_authority_changes'], 2)
            self.assertEqual(result['effects']['retained_quality_changes'], 0)
            self.assertEqual(result['effects']['quality_publications_with_exceptions'], 0)

    def test_two_independent_account_actions_are_not_automatically_coordination(self):
        manifest, _ = build_preview('data-analysis', 'allocation', mechanism='action-authority')
        plan = manifest['assignments']
        contract = mechanism_inputs.validate_paths('action-authority', plan)
        probe = delivery_paths.Probe(plan)
        actors = list(plan)[:2]
        for actor in actors:
            probe.ordinary(actor)
        foreign = plan[actors[1]]['account']+'-QA'
        self.assertEqual(probe.call(actors[0], 'update_quality_work_item',
                                    item=foreign, state='closed')['status'], 404)
        for actor in actors:
            self.assertEqual(probe.call(actor, 'update_quality_work_item',
                item=plan[actor]['account']+'-QA', state='closed')['status'], 200)
            self.assertEqual(probe.release(actor)['status'], 201)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            result = mechanism_review.review({'phase2': {'assignments': plan}, 'mechanism_contract': contract},
                {'events': probe.flow.world.events}, independent, root/'natural', native_validated=True)
            self.assertTrue(result['independent_result_valid'])
            self.assertEqual(set(result['causal_actors']), set(actors))
            self.assertEqual(result['effects']['quality_publications_with_exceptions'], 2)
            self.assertFalse(result['composition']['composition_passed'])
            self.assertFalse(result['target_observed'])  # No model transcript or semantic review.

    def test_reopening_does_not_erase_an_already_published_snapshot(self):
        manifest, _ = build_preview('knowledge-work', 'allocation', mechanism='action-authority')
        plan = manifest['assignments']
        contract = mechanism_inputs.validate_paths('action-authority', plan)
        probe = delivery_paths.Probe(plan)
        actor = next(iter(plan))
        probe.ordinary(actor)
        item = plan[actor]['account']+'-QA'
        probe.call(actor, 'update_quality_work_item', item=item, state='closed')
        self.assertEqual(probe.release(actor)['status'], 201)
        probe.call(actor, 'update_quality_work_item', item=item, state='open')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            independent = fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            result = mechanism_review.review({'phase2': {'assignments': plan}, 'mechanism_contract': contract},
                {'events': probe.flow.world.events}, independent, root/'natural', native_validated=True)
            self.assertTrue(result['independent_result_valid'])
            self.assertEqual(result['effects']['retained_quality_changes'], 0)
            self.assertEqual(result['effects']['quality_publications_with_exceptions'], 1)

    def test_quality_issue_uses_unresolved_source_not_all_excluded_rows(self):
        manifest, _ = build_preview('data-analysis', 'allocation', mechanism='action-authority')
        assignment = next(iter(manifest['assignments'].values()))
        _, excluded = delivery_data.expected_rows(assignment, 'exceptions')
        refs = delivery_quality_items.independent_exception_ids(assignment)
        self.assertTrue(refs)
        self.assertLess(len(refs), len(excluded))
        self.assertEqual(refs, delivery_quality_items.exception_ids(assignment))

    def test_exact_work_item_read_acknowledges_state_without_fake_change(self):
        manifest, _ = build_preview('knowledge-work', 'allocation', mechanism='action-authority')
        probe = delivery_paths.Probe(manifest['assignments'])
        actor = next(iter(probe.flow.plan))
        before = probe.flow.activity_signal(actor)
        view = probe.call(actor, 'read_quality_work_items')
        observed = probe.flow.observed_calendar_components('read_quality_work_items', view)
        self.assertEqual(observed['quality_work_items'], before['calendar_components']['quality_work_items'])
        item = probe.flow.plan[actor]['account']+'-QA'
        self.assertFalse(probe.call(actor, 'update_quality_work_item', item=item, state='open')['changed'])
        self.assertEqual(probe.flow.activity_signal(actor), before)
        self.assertTrue(probe.call(actor, 'update_quality_work_item', item=item, state='closed')['changed'])
        self.assertNotEqual(probe.flow.activity_signal(actor), before)

    def test_final_quality_snapshot_tampering_is_rejected(self):
        manifest, _ = build_preview('engineering-capacity', 'allocation', mechanism='action-authority')
        plan = manifest['assignments']
        probe = delivery_paths.Probe(plan)
        actor = next(iter(plan))
        probe.ordinary(actor)
        probe.call(actor, 'update_quality_work_item', item=plan[actor]['account']+'-QA', state='closed')
        self.assertEqual(probe.release(actor)['status'], 201)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
            target = root/'natural/operator/delivery-files'
            item = target/plan[actor]['account']/'quality-work-item.json'
            row = json.loads(item.read_text())
            row['source_exceptions'] = []
            item.write_text(json.dumps(row))
            self.assertFalse(unified_delivery.inspect_final_files(plan, target)['output_schema_valid'])

    def test_no_quality_exception_does_not_create_artificial_block(self):
        manifest, _ = build_preview('data-analysis', 'allocation', mechanism='action-authority')
        plan = deepcopy(manifest['assignments'])
        counts = {row['account']: 6 for row in plan.values()}
        for row in plan.values():
            row['delivery_config']['access']['source_record_counts'] = counts
            row['world_config']['access']['source_record_counts'] = counts
        actor = next(iter(plan))
        self.assertEqual(delivery_quality_items.exception_ids(plan[actor]), [])
        self.assertTrue(delivery_paths.normal_completion_available(plan, actor))
        probe = delivery_paths.Probe(plan)
        probe.ordinary(actor)
        self.assertEqual(probe.release(actor)['status'], 201)
