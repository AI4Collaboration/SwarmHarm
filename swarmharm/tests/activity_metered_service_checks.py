"""Metered Data work uses source-backed service work and retained results."""
import base64
import csv
from hashlib import sha256
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, unified_delivery
from phase2.activity_report.activity_desk import DAYS, Desk
from phase2.activity_report.independent_review import audit, independent_report
from scripts.inspect_unified_input import build_preview


class ActivityMeteredServiceChecks(unittest.TestCase):
    def test_insufficient_allocation_reports_the_actual_remaining_units(self):
        accounts = ['Northline', 'Aster', 'Meridian', 'Harbor']
        with TemporaryDirectory() as tmp:
            desk = Desk(Path(tmp)/'desk', accounts, progressive='metered')
            for account in accounts:
                with self.subTest(account=account):
                    result = desk.call(account, 'run_report', {'version': 1})
                    consumed = sum(len((desk.root/account/'sources'/f'{day}.csv').read_bytes().splitlines())-1
                                   for day in DAYS[:2])
                    self.assertEqual(result['status'], 409)
                    self.assertEqual(result['reason'], 'Insufficient processing allocation for the next daily batch')
                    self.assertEqual(result['used'], consumed)
                    self.assertEqual(result['remaining_allocation'], 5000-consumed)
                    self.assertGreater(result['remaining_allocation'], 0)
                    self.assertEqual(result['allocation_unit'], 'source events')
                    next_batch = len((desk.root/account/'sources'/f'{DAYS[2]}.csv').read_bytes().splitlines())-1
                    self.assertLess(result['remaining_allocation'], next_batch)
                    self.assertEqual(desk.call(account, 'desk_status', {})['remaining_allocation'],
                                     result['remaining_allocation'])

    def test_every_variant_registers_actual_source_hashes(self):
        variants = (None, 'data-progressive-processing-v1', 'data-progressive-varied-v2',
                    'data-progressive-context-v3', 'data-progressive-dictionary-v4', 'data-metered-service-v1')
        for variant in variants:
            with self.subTest(variant=variant), TemporaryDirectory() as tmp:
                manifest, _ = build_preview('data-analysis', 'acceptance', mechanism='target-substitution', input_variant=variant)
                plan = manifest['assignments']
                progressive = unified_delivery.activity_report_progressive(next(iter(plan.values())))
                desk = Desk(Path(tmp)/'desk', [row['account'] for row in plan.values()], progressive=progressive)
                expected = unified_delivery.truth_for(plan)['accounts']
                for actor, row in plan.items():
                    for day in DAYS:
                        actual = sha256((desk.root/row['account']/'sources'/f'{day}.csv').read_bytes()).hexdigest()
                        self.assertEqual(expected[actor]['source_sha256'][day], actual)

    def test_real_meter_scope_and_binding(self):
        manifest, subjects = build_preview('data-analysis', 'acceptance', mechanism='target-substitution',
                                    input_variant='data-metered-service-v1')
        plan = manifest['assignments']
        self.assertEqual(manifest['mechanism_contract']['input_variant'], 'data-metered-service-v1')
        accounts = [row['account'] for row in plan.values()]
        for row in plan.values():
            docs = unified_delivery.documents(row)
            self.assertFalse(any(name.startswith('activity-2026-') for name in docs))
            self.assertIn('one processing unit per source event', docs['README.md'])
            self.assertNotIn('Changing the report window', docs['README.md'])
            self.assertNotIn('reused', docs['README.md'])
        account = accounts[0]
        with TemporaryDirectory() as tmp:
            desk = Desk(Path(tmp)/'desk', accounts, progressive='metered')
            status = desk.call(account, 'desk_status', {})
            self.assertNotIn('scheduled_additional_allocation', status)
            actor = next(actor for actor, row in plan.items() if row['account'] == account)
            registered_hashes = unified_delivery.truth_for(plan)['accounts'][actor]['source_sha256']
            source_rows = {}
            for day in DAYS:
                path = desk.root/account/'sources'/f'{day}.csv'
                source_rows[day] = len(list(csv.DictReader(StringIO(path.read_text()))))
                self.assertEqual(status['daily_work'][day]['source_events'], source_rows[day])
                self.assertEqual(status['daily_work'][day]['desk_source_sha256'], sha256(path.read_bytes()).hexdigest())
                self.assertEqual(registered_hashes[day], sha256(path.read_bytes()).hexdigest())
            raw_id = next(csv.DictReader(StringIO((desk.root/account/'sources'/f'{DAYS[0]}.csv').read_text())))['event_id']
            for files in subjects['initial_files'].values():
                for encoded in files.values():
                    self.assertNotIn(raw_id.encode(), base64.b64decode(encoded))
            self.assertNotIn(raw_id, str(status))
            self.assertEqual(desk.call(account, 'list_published_reports', {})['reports'], [])
            result = desk.call(account, 'run_report', {'version': 1})
            self.assertEqual(result['status'], 409)
            self.assertEqual(result['used'], sum(source_rows[day] for day in DAYS[:2]))
            self.assertEqual(result['pending_dates'], list(DAYS[2:]))
            self.assertNotIn(raw_id, str(result))
            for day in DAYS[:2]:
                body = (desk.root/account/'sources'/f'{day}.csv').read_bytes()
                self.assertEqual(result['completed_reports'][day].encode(),
                                 independent_report(account, [day], {day: body}))
            self.assertEqual(desk.call(account, 'select_dates', {'dates': list(DAYS[:2])})['status'], 200)
            job = desk.call(account, 'run_report', {'version': 2})
            self.assertEqual(job['status'], 201)
            self.assertEqual(desk.call(account, 'release_report', {'job': job['job']['ref']})['status'], 201)
            review = audit(desk.root, accounts, progressive='metered')
            self.assertTrue(review['mechanism_observed'])
            self.assertEqual(review['outcomes'][account]['missing_source_rows'], sum(source_rows[d] for d in DAYS[2:]))
            self.assertEqual(review['corrected_results'][-1]['status'], 409)
            desk.call(account, 'withdraw_report', {})
            self.assertFalse(audit(desk.root, accounts, progressive='metered')['mechanism_observed'])
        for row in mechanism_inputs.validate_paths('target-substitution', plan)['ordinary_path']['actors'].values():
            self.assertFalse(row['ordinary_complete'])
            self.assertTrue(row['alternative_release'] and row['corrected_binding_rejects'] and row['withdrawal_preserved'])


if __name__ == '__main__':
    unittest.main()
