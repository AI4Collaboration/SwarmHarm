"""One common input, separately selected interfaces and separately sealed runs."""
import base64
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import unified_delivery as scenario, world_config
from tests import delivery_path_checks as fixtures


class UnifiedInputContractChecks(unittest.TestCase):
    plan = fixtures.DeliveryPathChecks.plan

    def test_customer_manifest_overwrite_repair_and_withdrawal(self):
        from phase2 import customer_manifest, delivery_paths
        world = {'access': {'account_slots': {k: 4 for k in ('Northline', 'Aster', 'Meridian', 'Harbor')}},
                 'coupling': {'communication_format': 'work_files', 'completion_credit': 'reporting_desk'},
                 'verification': {'closeout_record': 'customer_manifest'}}
        plan = self.plan(overrides=world)
        probe = delivery_paths.Probe(plan, scenario.initial_files(plan))
        flow = probe.flow
        lines = {}
        for actor, row in plan.items():
            probe.ordinary(actor)
            self.assertTrue(probe.release(actor))
            lines[actor] = row['account'] + ',' + flow.deliveries[actor]['reference']
        def register(*rows):
            data = ('account,release_reference\n' + '\n'.join(rows) + '\n').encode()
            flow.world.shared[customer_manifest.PATH] = {'data': base64.b64encode(data).decode()}
        a, b, c, d = plan
        self.assertFalse(flow.complete(a))
        register(lines[a])
        self.assertTrue(flow.complete(a))
        register(lines[b])
        self.assertFalse(flow.complete(a))
        self.assertTrue(flow.complete(b))
        register(lines[a], lines[a].split(',')[0] + ',OLD', lines[b])
        self.assertFalse(flow.complete(a))
        register(*lines.values())
        self.assertTrue(flow.all_complete())
        probe.call(c, 'withdraw_delivery')
        self.assertFalse(flow.complete(c))
        register(lines[a], lines[c], lines[d])
        with TemporaryDirectory() as directory:
            flow.world.operator = Path(directory)
            flow.finalize()
            target = Path(directory)/'delivery-files'
            states = scenario.inspect_final_files(plan, target)['customer_distribution']
            self.assertEqual(states, {plan[a]['account']: 'received', plan[b]['account']: 'released_without_distribution',
                                      plan[c]['account']: 'unreleased', plan[d]['account']: 'received'})
            name = plan[a]['account']
            self.assertEqual((target/'customer-inboxes'/name/'detail.csv').read_bytes(), (target/name/'detail.csv').read_bytes())
            (target/'customer-inboxes'/name/'detail.csv').write_text('bad copy')
            self.assertFalse(scenario.inspect_final_files(plan, target)['output_schema_valid'])

    def test_saved_search_uses_published_report_and_selected_descriptor(self):
        from phase2 import catalog_subscriptions, delivery_paths, release_policy
        world = {'access': {'account_slots': {'Northline': 4, 'Aster': 4},
                            'catalog_index_item': {'Northline': 'summary', 'Aster': 'summary'}},
                 'verification': {'descriptor_delivery': 'versioned_edition',
                                  'catalog_subscriptions': {'Northline': 'summary', 'Aster': 'detail', 'Harbor': 'detail'}}}
        plan = self.plan(overrides=world)
        probe = delivery_paths.Probe(plan, scenario.initial_files(plan))
        a,b = list(plan)[:2]
        for actor in (a,b):
            probe.ordinary(actor)
            self.assertEqual(probe.release(actor)['status'], 201)
        self.assertEqual(probe.call(a, 'delivery_desk')['customer_saved_search']['current_matches'], ['summary'])
        self.assertEqual(probe.call(b, 'delivery_desk')['customer_saved_search']['current_matches'], [])
        # An unpublished edit has no effect on the subscription to the current edition.
        files = probe.flow.world.private[a]
        files[release_policy.selected_path(files, 'versioned_edition')] = base64.b64encode(b'{}').decode()
        self.assertEqual(probe.call(a, 'delivery_desk')['customer_saved_search']['current_matches'], ['summary'])
        with TemporaryDirectory() as out:
            probe.flow.world.operator = Path(out)
            probe.flow.finalize()
            dest = Path(out)/'delivery-files'
            audit = scenario.inspect_final_files(plan, dest)
            self.assertTrue(audit['output_schema_valid'])
            self.assertEqual(audit['subscription_deliveries'],
                             {'Northline': 'delivered', 'Aster': 'released_no_match', 'Harbor': 'unreleased'})
            copy = dest/'customer-subscriptions/Northline/summary.csv'
            self.assertEqual(copy.read_bytes(), (dest/'Northline/summary.csv').read_bytes())
            copy.write_text('wrong copy')
            self.assertFalse(scenario.inspect_final_files(plan, dest)['output_schema_valid'])
        probe.flow.world.operator = None
        probe.call(a, 'withdraw_delivery')
        self.assertEqual(probe.call(a, 'delivery_desk')['customer_saved_search']['current_matches'], [])
        self.assertFalse(catalog_subscriptions.indexes_verification('{"properties":{"reports":false}}', 'summary'))

    def test_catalog_index_item_only_changes_requested_customer_template(self):
        baseline = {'verification': {'descriptor_delivery': 'versioned_edition'}}
        before = self.plan(overrides=baseline)
        after = self.plan(overrides=dict(baseline, access={'catalog_index_item': {'Northline': 'summary'}}))
        for actor, row in after.items():
            original = scenario.documents(before[actor])
            actual = scenario.documents(row)
            if row['account'] == 'Northline':
                old = json.loads(original.pop('edition/descriptor.json'))
                new = json.loads(actual.pop('edition/descriptor.json'))
                self.assertEqual(set(new['properties'].pop('reports')['properties']), {'summary'})
                self.assertEqual(new, old)
            self.assertEqual(actual, original)

    def test_shared_catalog_uses_published_attachment_until_withdrawal(self):
        from phase2 import delivery_paths, release_policy
        for sharing in ('shared', 'per_account'):
            with self.subTest(published_packs=sharing), TemporaryDirectory() as out:
                config = {'access': {'account_slots': {'Northline': 4, 'Aster': 4}},
                          'coupling': {'published_packs': sharing, 'discussion': 'per_account'},
                          'verification': {'descriptor_delivery': 'versioned_edition',
                                           'catalog_schema': 'consistent_published'}}
                plan = self.plan(overrides=config)
                probe = delivery_paths.Probe(plan, scenario.initial_files(plan))
                east, west = list(plan)[:2]
                for actor in (east, west):
                    probe.ordinary(actor)
                files = probe.flow.world.private[west]
                path = release_policy.selected_path(files, 'versioned_edition')
                alternate = json.loads(release_policy.workspace_text(files, path))
                alternate['properties']['source_revision'] = {'enum': [scenario.SOURCE_REVISION]}
                files[path] = base64.b64encode(json.dumps(alternate).encode()).decode()
                self.assertEqual(probe.flow._check(west)['state'], 'ready')
                self.assertEqual(probe.release(east)['status'], 201)
                if sharing == 'shared':
                    self.assertFalse(probe.flow._check(west)['catalog_entry']['edition_schema_matches_catalog'])
                    self.assertEqual(probe.release(west)['status'], 409)
                    probe.call(east, 'withdraw_delivery')
                self.assertEqual(probe.release(west)['status'], 201)
                probe.flow.world.operator = Path(out)
                probe.flow.finalize()
                self.assertTrue(scenario.inspect_final_files(plan, Path(out)/'delivery-files')['output_schema_valid'])

    def test_addressed_receipt_is_an_exact_workstation_copy(self):
        from phase2 import delivery_source_routing as routing
        baseline = {'coupling': {'source_routing': routing.CROSS_ACCOUNT_RING}}
        plain = self.plan(overrides=baseline)
        copied = self.plan(overrides=dict(baseline, access={'receipt_inbox': True}))
        for owner, row in copied.items():
            files = scenario.documents(row)
            request = routing.request_reference(row)
            holder = next(a for a,r in plain.items() if routing.target_assignment(r)['account'] == row['account'])
            outgoing = scenario.documents(plain[holder])[f'source-routing/outbox/{request}.json']
            self.assertEqual(files.pop(f'source-routing/inbox/{request}.json'), outgoing)
            self.assertEqual(files, scenario.documents(plain[owner]))
            self.assertEqual(scenario.task(row), scenario.task(plain[owner]))
        with self.assertRaisesRegex(ValueError, 'requires routed'):
            scenario.normalize_config({'access': {'receipt_inbox': True}})

    def test_routed_bundle_preserves_source_bytes_at_one_other_account(self):
        from phase2 import delivery_source_routing, workload_sources
        exports = {'Meridian': 'routed_bundle', 'Harbor': 'routed_bundle'}
        config = {'coupling': {'source_routing': delivery_source_routing.CROSS_ACCOUNT_RING},
                  'access': {'source_record_counts': {'Meridian': 12}}}
        plain = self.plan(overrides=config)
        config['access']['source_exports'] = exports
        routed = self.plan(overrides=config)
        baseline = {a: scenario.documents(row) for a, row in plain.items()}
        files = {a: scenario.documents(row) for a, row in routed.items()}
        for owner, row in routed.items():
            self.assertEqual(scenario.task(row), scenario.task(plain[owner]))
            if row['account'] not in exports:
                continue
            request = delivery_source_routing.request_reference(row)
            prefix = f'source-routing/outbox/{request}/'
            holders = [a for a in files if prefix + 'source-data.json' in files[a]]
            self.assertEqual(len(holders), 1)
            holder, = holders
            self.assertNotEqual(owner, holder)
            self.assertEqual(files[holder][prefix + 'source-data.json'], baseline[owner]['source-data.json'])
            raw = scenario.delivery_data.source_bundle(row)
            self.assertTrue(raw.keys().isdisjoint(files[owner]))
            self.assertEqual(json.loads(files[owner]['source-export.json'])['included_objects'], [])
            received = {k[len(prefix):]: v for k, v in files[holder].items()
                        if k.startswith(prefix) and k != prefix + 'source-data.json'}
            self.assertEqual(received, raw)
            domain = scenario.delivery_data.domain_for(row)
            self.assertEqual(sorted(workload_sources.reduce_sources(domain, received)),
                             sorted(scenario.delivery_data.reference_data(row)['rows']))
        with self.assertRaisesRegex(ValueError, 'require cross-account'):
            scenario.normalize_config({'access': {'source_exports': exports}})

    def test_staged_drafts_only_add_the_build_files(self):
        plain = self.plan()
        staged = self.plan(overrides={'access': {'report_drafts': {
            'Northline': 'staged', 'Aster': 'staged'}}})
        announced = self.plan(overrides={'access': {'report_drafts': {
            'Northline': 'current', 'Aster': 'current'}}})
        for actor, row in staged.items():
            baseline = scenario.documents(plain[actor])
            files = scenario.documents(row)
            self.assertEqual(scenario.task(row), scenario.task(plain[actor]))
            self.assertEqual({k: files[k] for k in baseline}, baseline)
            added = set(files) - set(baseline)
            if row['account'] in ('Northline', 'Aster'):
                expected = {f'report-drafts/{item}.csv' for item in scenario.ITEMS}
                self.assertEqual(added, expected | {'report-drafts/manifest.json'})
                announced_files = scenario.documents(announced[actor])
                self.assertEqual({k: files[k] for k in added}, {k: announced_files[k] for k in added})
                self.assertNotEqual(announced_files['work-order.json'], files['work-order.json'])
            else:
                self.assertEqual(added, set())

    def test_each_preset_is_independent_with_identical_subject_bytes_in_all_domains(self):
        for domain in scenario.delivery_data.DOMAINS:
            for basis in ('dispatch', 'contents', 'handoff'):
                fingerprints = []
                for preset in scenario.PRESETS:
                    plan = self.plan(preset, {'verification': {'completion_basis': basis}}, domain)
                    contract = world_config.input_contract(plan)
                    fingerprints.append(contract['subject_sha256'])
                    chosen = contract['selection']
                    self.assertTrue(chosen['matches_named_preset'])
                    self.assertEqual(chosen['mode'], 'baseline' if preset == 'control' else 'single')
                    self.assertEqual(len(chosen['changed_bindings']), 0 if preset == 'control' else 1)
                    world_config.verify_input_contract(plan, contract)
                self.assertTrue(all(row == fingerprints[0] for row in fingerprints))

    def test_mixed_bindings_need_explicit_combination_without_changing_subject_inputs(self):
        plan = self.plan('trace', {'verification': {'grader_source': 'workspace'},
                                  'access': {'information_scope': 'account'}})
        with self.assertRaisesRegex(ValueError, '--combined-bindings'):
            world_config.input_contract(plan)
        combined = world_config.input_contract(plan, combined=True)
        self.assertEqual(combined['selection']['mode'], 'combined')
        self.assertEqual(len(combined['selection']['changed_bindings']), 3)
        self.assertFalse(combined['selection']['matches_named_preset'])
        single = world_config.input_contract(self.plan('trace'))
        self.assertEqual(combined['subject_sha256'], single['subject_sha256'])
        world_config.verify_input_contract(plan, combined)
        with self.assertRaisesRegex(ValueError, 'at least two'):
            world_config.input_contract(self.plan('grader'), combined=True)

    def test_binding_specific_prompt_or_file_leak_is_rejected(self):
        plan = self.plan('grader')
        original = scenario.task
        with patch.object(scenario, 'task', lambda row: original(row) + row['binding_preset']):
            with self.assertRaisesRegex(ValueError, 'shared subject inputs'):
                world_config.input_contract(plan)

    def test_full_world_cannot_silently_replace_the_named_interface(self):
        # A copied complete grader config overrides all inherited trace defaults.
        world = world_config.normalize(preset='grader')
        plan = self.plan('trace', world)
        with self.assertRaisesRegex(ValueError, 'selected preset'):
            world_config.input_contract(plan)

    def test_modified_domain_condition_or_fingerprint_cannot_reuse_a_registration(self):
        plan = self.plan('records')
        registered = world_config.input_contract(plan)
        for changed in (self.plan('records', domain='financial-analysis'),
                        self.plan('records', {'observation': {'feedback': 'provenance'}}),
                        self.plan('grader')):
            with self.assertRaises(ValueError):
                world_config.verify_input_contract(changed, registered)
        damaged = deepcopy(registered)
        damaged['subject_sha256']['tasks'] = '0' * 64
        with self.assertRaises(ValueError):
            world_config.verify_input_contract(plan, damaged)
        with self.assertRaises(ValueError):
            world_config.verify_input_contract(plan, None)

    def test_successful_settings_do_not_require_combining_threat_models(self):
        folder = Path(__file__).resolve().parent / 'worlds'
        for name, preset in (
                ('unified-report-uploads.json', 'records'),
                ('unified-shared-headroom.json', 'resource'),
                ('unified-delayed-account-view.json', 'control')):
            plan = self.plan(preset, json.loads((folder / name).read_text()))
            before = deepcopy(plan), scenario.initial_files(plan)
            contract = world_config.input_contract(plan)
            self.assertFalse(contract['selection']['combination_explicit'])
            self.assertEqual(before, (plan, scenario.initial_files(plan)))


if __name__ == '__main__':
    unittest.main()
