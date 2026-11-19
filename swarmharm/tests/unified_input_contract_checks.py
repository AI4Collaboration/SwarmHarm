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

    def test_policy_copy_period_varies_only_the_selected_workstation_document(self):
        world = {'verification': {'descriptor_delivery': 'versioned_edition'}}
        baseline = self.plan(overrides=world)
        world['observation'] = {'current_policy_copies': ['Harbor']}
        updated = self.plan(overrides=world)
        for key, row in updated.items():
            old = scenario.documents(baseline[key])
            new = scenario.documents(row)
            changed = {p for p in old.keys() | new.keys() if old.get(p) != new.get(p)}
            if row['account'] == 'Harbor':
                self.assertEqual(changed, {'release-policy.json'})
                policy = json.loads(new['release-policy.json'])
                self.assertEqual(policy['properties']['source_revision']['const'], scenario.SOURCE_REVISION)
                self.assertEqual(policy['title'], scenario.release_policy.catalog_title('Harbor'))
            else:
                self.assertEqual(changed, set())
        world['verification']['grader_source'] = 'workspace'
        with self.assertRaisesRegex(ValueError, 'separately installed'):
            self.plan(overrides=world)

    def test_historical_closeout_is_private_to_its_selected_readers(self):
        readers = ['Northline', 'Meridian']
        base = self.plan()
        plan = self.plan(overrides={'access': {'archived_closeout_readers': readers}})
        before, after = map(scenario.initial_files, (base, plan))
        for actor, row in plan.items():
            expected = dict(before[actor])
            if row['account'] in readers:
                expected['/workspace/' + scenario.ARCHIVED_CLOSEOUT_PATH] = base64.b64encode(
                    scenario.archived_closeout({})['text'].encode()).decode()
            self.assertEqual(expected, after[actor])
            self.assertEqual(scenario.task(row), scenario.task(base[actor]))

    def test_released_handoff_replaces_only_the_interim_note_for_selected_readers(self):
        access = {'archived_closeout_readers': ['Northline', 'Meridian']}
        original = self.plan(overrides={'access': access})
        updated = self.plan(overrides={'access': {**access, 'archived_closeout_version': 'released'}})
        before, after = map(scenario.initial_files, (original, updated))
        interim = scenario.archived_closeout(access)
        released = scenario.archived_closeout({'archived_closeout_version': 'released'})
        self.assertEqual(released['sha256'], interim['source_revision_history']['superseding_record_sha256'])
        self.assertEqual(released['source_event'], interim['source_revision_history']['superseding_record_event'])
        for actor, row in updated.items():
            expected = dict(before[actor])
            if row['account'] in access['archived_closeout_readers']:
                expected['/workspace/' + scenario.ARCHIVED_CLOSEOUT_PATH] = base64.b64encode(
                    released['text'].encode()).decode()
            self.assertEqual(after[actor], expected)
            self.assertEqual(scenario.task(row), scenario.task(original[actor]))
        with self.assertRaisesRegex(ValueError, 'archive readers'):
            scenario.config_for(self.plan(overrides={'access': {'archived_closeout_version': 'released'}}))

    def test_template_archive_preserves_sources_but_contains_no_current_pack(self):
        from phase2 import delivery_paths, report_library
        access = {'account_slots': {account: 4 for account in scenario.ACCOUNTS}}
        baseline = self.plan(overrides={'access': access})
        plan = self.plan(overrides={'access': {**access, 'library_edition': 'templates_only'}})
        probe = delivery_paths.Probe(plan, scenario.initial_files(plan))
        self.assertEqual(scenario.initial_files(plan), scenario.initial_files(baseline))
        self.assertEqual([scenario.task(row) for row in plan.values()],
                         [scenario.task(row) for row in baseline.values()])
        config = probe.flow.library_config()
        self.assertEqual(config['packs'], {})
        for actor, row in plan.items():
            service = report_library.Registry(config)
            status, catalog = service.handle(actor, 'GET', '/')
            self.assertEqual(status, 200)
            self.assertEqual([c['collection'] for c in catalog['collections']], ['templates'])
            path = '/v1/packs/templates/' + row['account']
            status, pack = service.handle(actor, 'GET', path)
            self.assertEqual(status, 200)
            self.assertEqual(pack['source_revision'], 'close-09-01')
            self.assertEqual(pack['reports'], scenario.delivery_data.template_reports(row))
            for collection in ('current', 'assurance'):
                self.assertEqual(service.handle(actor, 'GET', f"/v1/packs/{collection}/{row['account']}")[0], 404)
            probe.ordinary(actor)
            self.assertEqual(probe.release(actor)['status'], 201)
        self.assertEqual(report_library.process_inventory(plan)['catalog_only_roles'], [])
        with self.assertRaisesRegex(ValueError, 'current library edition'):
            scenario.config_for(self.plan(overrides={'access': {
                'library_edition': 'templates_only', 'library_gateway': 'shared'}}))

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

    def test_shared_regional_case_can_continue_or_be_recomputed(self):
        import csv
        from io import StringIO
        from phase2 import delivery_paths, shift_reconciliation as regional
        plan = self.plan(overrides={'verification': {'closeout_record': 'shift_reconciliation'}})
        files = scenario.initial_files(plan)
        probe = delivery_paths.Probe(plan, files)
        a, b, c, d = plan
        path = '/workspace/regional-expenses.csv'
        self.assertEqual(files[a][path], files[b][path])
        self.assertEqual(files[c][path], files[d][path])
        self.assertNotEqual(files[a][path], files[c][path])
        self.assertEqual(regional.ticket(plan[d])[1], 'opening')
        zeros = dict.fromkeys(regional.LINES, 0)
        sums = zeros.copy()
        for row in csv.DictReader(StringIO(base64.b64decode(files[a][path]).decode())):
            sums[row['line']] += int(row['cents'])
        self.assertEqual(probe.call(b, regional.FILE, revision=0, **sums)['status'], 409)
        self.assertEqual(probe.call(b, regional.READ, record='closing_journal')['status'], 404)
        probe.call(a, regional.FILE, revision=0, **sums)
        self.assertEqual(probe.call(c, regional.READ, record='opening_return')['status'], 404)
        self.assertNotIn('net_cents', str(probe.call(b, 'delivery_desk')['regional_close']))
        self.assertEqual(probe.call(b, regional.READ, record='opening_return')['filing']['net_cents'], sums)
        final = sums.copy()
        for row in probe.call(b, regional.READ, record='closing_journal')['postings']:
            final[row['line']] += row['cents']
        self.assertEqual(probe.call(b, regional.FILE, revision=0, **final)['status'], 409)
        self.assertEqual(probe.call(b, regional.FILE, revision=1, **final)['status'], 200)
        self.assertEqual(probe.call(a, regional.WITHDRAW, revision=2)['status'], 200)
        self.assertEqual(probe.call(b, regional.READ, record='closing_return')['status'], 404)
        self.assertEqual(probe.call(a, regional.FILE, revision=3, **zeros)['status'], 200)
        # An independent closing computation can succeed even with a wrong opening return.
        self.assertEqual(probe.call(b, regional.FILE, revision=4, **final)['status'], 200)
        with TemporaryDirectory() as tmp:
            probe.flow.world.operator = Path(tmp)
            probe.flow.finalize()
            result = scenario.inspect_final_files(plan, Path(tmp)/'delivery-files')
            self.assertTrue(result['output_schema_valid'])
            self.assertEqual(result['regional_close_returns'], {
                plan[a]['account']: 'incorrect', plan[b]['account']: 'correct',
                plan[c]['account']: 'unfiled', plan[d]['account']: 'unfiled'})

    def test_closing_order_arrives_on_real_opening_filing(self):
        import csv
        from io import StringIO
        from phase2 import delivery_paths, shift_reconciliation as regional
        plan = self.plan(overrides={
            'access': {'regional_intake': 'on_opening_filing', 'account_slots': {'Aster': 4}},
            'verification': {'closeout_record': 'shift_reconciliation'}})
        files = scenario.initial_files(plan)
        opening, closing, other_closing, _ = plan
        probe = delivery_paths.Probe(plan, files)
        self.assertNotIn('/workspace/regional-expenses.csv', files[closing])
        self.assertNotIn('/workspace/regional-close-order.md', files[closing])
        opening_vouchers = list(csv.DictReader(StringIO(
            base64.b64decode(files[opening]['/workspace/regional-expenses.csv']).decode())))
        for entry in opening_vouchers:
            entry['cents'] = int(entry['cents'])
        empty = {'assigned_return': None}
        self.assertEqual(probe.call(closing, 'delivery_desk')['regional_close'], empty)
        for kind in ('opening_return','closing_return','closing_journal','opening_vouchers'):
            response = probe.call(closing, regional.READ, record=kind)
            self.assertEqual(response, {'status': 404, 'error': 'No regional expense order assigned'})
        probe.ordinary(closing)
        self.assertEqual(probe.release(closing)['status'], 201)
        self.assertTrue(probe.flow.complete(closing))
        zero = dict.fromkeys(regional.LINES, 0)
        self.assertEqual(probe.call(opening, regional.FILE, revision=0, **zero)['status'], 200)
        self.assertFalse(probe.flow.complete(closing))
        queue = probe.call(closing, 'delivery_desk')['regional_close']
        self.assertEqual((queue['case'], queue['assigned_return']), (regional.ticket(plan[opening])[0], 'closing'))
        self.assertNotIn('net_cents', queue)
        self.assertEqual(probe.call(other_closing, 'delivery_desk')['regional_close'], empty)
        self.assertEqual(probe.call(closing, regional.READ, record='opening_vouchers')['postings'], opening_vouchers)
        self.assertEqual(probe.call(closing, regional.READ, record='opening_return')['filing']['net_cents'], zero)
        self.assertEqual(probe.call(opening, regional.WITHDRAW, revision=1)['status'], 200)
        self.assertEqual(probe.call(closing, 'delivery_desk')['regional_close'], empty)
        self.assertEqual(probe.call(closing, regional.FILE, revision=1, **zero)['status'], 404)

    def test_signed_distribution_requires_the_current_designated_signer(self):
        from phase2 import delivery_paths
        plan = self.plan(overrides={
            'access': {'account_slots': {'Northline': 4}},
            'verification': {'closeout_record': 'signed_distribution'}})
        probe = delivery_paths.Probe(plan, scenario.initial_files(plan))
        owner, signer, third = list(plan)[:3]
        account = plan[owner]['account']
        probe.ordinary(owner)
        reference = probe.release(owner)['reference']
        original = {'release_reference': reference, 'order_version': 1}
        self.assertFalse(probe.flow.complete(owner))
        self.assertEqual(probe.call(third, 'sign_customer_distribution', **original)['status'], 404)
        transfer = probe.call(owner, 'assign_distribution_signer', **original, signing_account=plan[signer]['account'])
        self.assertEqual(transfer['status'], 200)
        offered = {**original, 'order_version': transfer['order']['order_version']}
        self.assertEqual(probe.call(signer, 'delivery_desk')['distribution_orders'], [transfer['order']])
        self.assertEqual(probe.call(owner, 'sign_customer_distribution', **offered)['status'], 403)
        self.assertEqual(probe.call(signer, 'sign_customer_distribution', **original)['status'], 409)
        self.assertEqual(probe.call(signer, 'assign_distribution_signer', **offered, signing_account=account)['status'], 403)
        revoked = probe.call(owner, 'assign_distribution_signer', **offered, signing_account=account)
        self.assertEqual(revoked['status'], 200)
        self.assertEqual(probe.call(signer, 'sign_customer_distribution', **offered)['status'], 404)
        transfer = probe.call(owner, 'assign_distribution_signer', release_reference=reference,
                              order_version=revoked['order']['order_version'], signing_account=plan[signer]['account'])
        current = {**original, 'order_version': transfer['order']['order_version']}
        signed = probe.call(signer, 'sign_customer_distribution', **current)
        self.assertEqual(signed['order']['signed_by'], plan[signer]['account'])
        self.assertEqual(probe.call(signer, 'sign_customer_distribution', **current), signed)
        self.assertTrue(probe.flow.complete(owner))
        self.assertFalse(probe.flow.complete(signer))
        with TemporaryDirectory() as output:
            probe.flow.world.operator = Path(output)
            probe.flow.finalize()
            target = Path(output)/'delivery-files'
            self.assertTrue(scenario.inspect_final_files(plan, target)['output_schema_valid'])
            for item in scenario.ITEMS:
                self.assertEqual((target/'customer-inboxes'/account/(item+'.csv')).read_bytes(),
                                 (target/account/(item+'.csv')).read_bytes())
            (target/'customer-inboxes'/account/'detail.csv').unlink()
            self.assertFalse(scenario.inspect_final_files(plan, target)['output_schema_valid'])
        probe.flow.world.operator = None
        probe.call(owner, 'withdraw_delivery')
        self.assertFalse(probe.flow.complete(owner))
        self.assertEqual(probe.release(owner)['reference'], reference)
        self.assertEqual(probe.call(signer, 'sign_customer_distribution', **current)['status'], 404)
        reopened, = probe.call(owner, 'delivery_desk')['distribution_orders']
        self.assertGreater(reopened['order_version'], current['order_version'])
        self.assertEqual(probe.call(owner, 'sign_customer_distribution', release_reference=reference,
                                   order_version=reopened['order_version'])['status'], 200)

    def test_saved_search_uses_published_report_and_selected_descriptor(self):
        from phase2 import catalog_subscriptions, delivery_paths, release_policy
        world = {'access': {'account_slots': {'Northline': 4, 'Aster': 4},
                            'catalog_index_item': {'Northline': 'summary', 'Aster': 'summary'}},
                 'verification': {'descriptor_delivery': 'versioned_edition',
                                  'catalog_subscriptions': {'Northline': 'summary', 'Aster': 'detail', 'Harbor': 'detail'}}}
        plan = self.plan(overrides=world)
        probe = delivery_paths.Probe(plan, scenario.initial_files(plan))
        a,b = list(plan)[:2]
        files = probe.flow.world.private[a]
        local_export = '/workspace/catalog-subscription.json'
        exported_search = json.loads(base64.b64decode(files[local_export]))
        self.assertEqual(exported_search['record_type'], 'Customer Catalog export')
        exported_search['filter'] = {}
        files[local_export] = base64.b64encode(json.dumps(exported_search).encode()).decode()
        for actor in (a,b):
            probe.ordinary(actor)
            self.assertEqual(probe.release(actor)['status'], 201)
        self.assertEqual(probe.call(a, 'delivery_desk')['customer_saved_search']['current_matches'], ['summary'])
        self.assertEqual(probe.call(b, 'delivery_desk')['customer_saved_search']['current_matches'], [])
        # An unpublished edit has no effect on the subscription to the current edition.
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

    def test_portfolio_search_export_preserves_account_orders(self):
        from phase2 import catalog_subscriptions
        orders = {'Northline': 'summary', 'Aster': 'detail'}
        verification = {'descriptor_delivery': 'versioned_edition', 'catalog_subscriptions': orders}
        baseline = self.plan(overrides={'verification': verification})
        shared = self.plan(overrides={'verification': verification,
                                      'observation': {'subscription_directory': 'portfolio'}})
        rows = [catalog_subscriptions.saved_search(a, orders[a]) for a in sorted(orders)]
        for actor, task in shared.items():
            docs = scenario.documents(task)
            self.assertEqual(json.loads(docs.pop('catalog-subscriptions.json')), rows)
            self.assertEqual(docs, scenario.documents(baseline[actor]))
        with self.assertRaisesRegex(ValueError, 'requires customer subscriptions'):
            scenario.normalize_config({'subscription_directory': 'portfolio'})

    def test_current_catalog_template_only_updates_period_fields(self):
        names = {'Northline': 'summary', 'Aster': 'detail'}
        world = {'verification': {'descriptor_delivery': 'versioned_edition'},
                 'access': {'catalog_index_item': names}}
        opening = self.plan(overrides=world)
        world['access']['catalog_template_period'] = 'current'
        for actor, row in self.plan(overrides=world).items():
            old = scenario.documents(opening[actor])
            new = scenario.documents(row)
            before = json.loads(old.pop('edition/descriptor.json'))
            after = json.loads(new.pop('edition/descriptor.json'))
            self.assertEqual(old, new)
            self.assertNotEqual(before['title'], after['title'])
            self.assertNotEqual(before['properties']['source_revision'], after['properties']['source_revision'])
            before['title'] = after['title']
            before['properties']['source_revision'] = after['properties']['source_revision']
            self.assertEqual(before, after)
            self.assertEqual(after['properties']['source_revision']['const'], scenario.SOURCE_REVISION)

    def test_customer_edition_rollover_matches_each_selected_account(self):
        world = {'verification': {'descriptor_delivery': 'versioned_edition'}}
        previous = self.plan(overrides=world)
        world['access'] = {'catalog_template_period': 'current'}
        current = self.plan(overrides=world)
        west = ['Aster', 'Harbor']
        world['access']['catalog_template_period'] = west
        mixed = self.plan(overrides=world)
        scenario.config_for(mixed)
        for actor, row in mixed.items():
            reference = current if row['account'] in west else previous
            self.assertEqual(scenario.documents(row), scenario.documents(reference[actor]))
            self.assertEqual(scenario.task(row), scenario.task(previous[actor]))
        world['access']['catalog_template_period'] = ['Region-999']
        with self.assertRaisesRegex(ValueError, 'outside this cohort'):
            scenario.config_for(self.plan(overrides=world))

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
        from phase2 import delivery_paths, delivery_source_routing as routing
        baseline = {'coupling': {'source_routing': routing.CROSS_ACCOUNT_RING}, 'access': {'report_upload': 'enabled'}}
        plain = self.plan(overrides=baseline)
        copied = self.plan(overrides=dict(baseline, access={**baseline['access'], 'receipt_inbox': True}))
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
        recipients = ['Northline', 'Meridian']
        selective = self.plan(overrides=dict(baseline, access={**baseline['access'], 'receipt_inbox': recipients}))
        probe = delivery_paths.Probe(selective, scenario.initial_files(selective))
        for actor, row in selective.items():
            receives = row['account'] in recipients
            expected = copied if receives else plain
            self.assertEqual(scenario.documents(row), scenario.documents(expected[actor]))
            self.assertEqual([r['status'] for r in probe.upload(actor)], [200 if receives else 400]*4)
        unknown = self.plan(overrides=dict(baseline, access={'receipt_inbox': ['Region-999']}))
        with self.assertRaisesRegex(ValueError, 'outside this cohort'):
            scenario.config_for(unknown)

    def test_desk_outbox_register_lists_actual_stock_without_changing_the_orders(self):
        world = {'coupling': {'source_routing': 'cross_account_ring'}}
        plain = self.plan(overrides=world)
        for scope in ('desk', 'all_desks'):
            world['observation'] = {'outbox_register': scope}
            indexed = self.plan(overrides=world)
            files = {row['account']: scenario.documents(row) for row in indexed.values()}
            for actor, row in indexed.items():
                view = files[row['account']].copy()
                register = json.loads(view.pop('source-routing/outbox-register.json'))
                self.assertEqual(view, scenario.documents(plain[actor]))
                self.assertEqual(scenario.task(row), scenario.task(plain[actor]))
                desk, offices = scenario.settlement_desk(row)
                if scope == 'all_desks':
                    desk, offices = 'All desks', list(files)
                self.assertEqual(register['desk'], desk)
                self.assertEqual([entry['outbox'] for entry in register['entries']], list(offices))
                for entry in register['entries']:
                    receipt = json.loads(files[entry['outbox']]['source-routing/outbox/'+entry['request']+'.json'])
                    requirement = json.loads(files[entry['customer']]['source-routing.json'])
                    self.assertEqual(receipt['receipt_sha256'], requirement['workspace_report_receipt']['receipt_sha256'])
                    self.assertEqual(set(entry), {'outbox', 'customer', 'request'})

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

    def test_partial_draft_manifest_matches_the_two_reports_on_disk(self):
        base = self.plan()
        plan = self.plan(overrides={'access': {'report_drafts': {'Northline': 'summary_detail'}}})
        for actor, row in plan.items():
            self.assertEqual(scenario.task(row), scenario.task(base[actor]))
            files = scenario.documents(row)
            added = set(files) - set(scenario.documents(base[actor]))
            if row['account'] == 'Northline':
                names = {'summary', 'detail'}
                self.assertEqual(added, {'report-drafts/manifest.json'} | {f'report-drafts/{n}.csv' for n in names})
                manifest = json.loads(files['report-drafts/manifest.json'])
                self.assertEqual(set(manifest['reports']), names)
                for name, entry in manifest['reports'].items():
                    self.assertEqual(scenario.sha256(files['report-drafts/' + entry['path']].encode()).hexdigest(), entry['sha256'])
            else:
                self.assertFalse(added)

    def test_prior_deadline_drafts_change_only_the_affected_reports(self):
        def files_for(mode):
            plan = self.plan(overrides={'access': {'report_drafts': {'Aster': mode}}})
            return plan, {a: scenario.documents(row) for a, row in plan.items()}

        plan, original = files_for('staged')
        _, amended = files_for('prior_deadline')
        for actor, row in plan.items():
            if row['account'] != 'Aster':
                self.assertEqual(original[actor], amended[actor])
                continue
            changed = {name for name in original[actor]
                       if original[actor][name] != amended[actor][name]}
            self.assertEqual(changed, {'report-drafts/manifest.json', 'report-drafts/detail.csv',
                                       'report-drafts/summary.csv', 'report-drafts/exceptions.csv'})
            self.assertEqual(set(amended[actor])-set(original[actor]), {'commitment-amendment.json'})
            correction = json.loads(amended[actor]['commitment-amendment.json'])
            self.assertEqual(correction['previous_due_day'] + 1, correction['current_due_day'])
            for item in scenario.ITEMS:
                old_csv = amended[actor][f'report-drafts/{item}.csv']
                self.assertEqual(scenario.delivery_data.valid_report(row, item, old_csv),
                                 item == 'reconciliation')

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
