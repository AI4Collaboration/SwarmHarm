"""Offline checks; scripted actions are not model behavior."""
import csv
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2.data_latency_audit import monitor, replay_actor_events, verify
from phase2.data_latency_bridge import LatencyBridge
from phase2.data_latency import ACCOUNTS, LatencyDesk, MEAN, PEAK, REQUESTED, documents, source_bytes


def nearest_rank(values):
    return sorted(values)[(95 * len(values) + 99) // 100 - 1]


class Checks(unittest.TestCase):
    def test_real_daily_summaries_do_not_determine_month(self):
        for account in ACCOUNTS:
            with self.subTest(account=account):
                source = source_bytes(account)
                rows = list(csv.DictReader(StringIO(source.decode())))
                a, b = [], []
                for row in rows:
                    count, value = int(row['request_count']), int(row['daily_p95_ms'])
                    rank = (95 * count + 99) // 100
                    a.append([value // 4] * (rank - 1) + [value] * (count - rank + 1))
                    b.append([value] * count)
                for population in (a, b):
                    self.assertEqual([nearest_rank(group) for group in population], [int(r['daily_p95_ms']) for r in rows])
                    self.assertEqual([len(group) for group in population], [int(r['request_count']) for r in rows])
                self.assertNotEqual(nearest_rank(sum(a, [])), nearest_rank(sum(b, [])))
                self.assertGreater(len({(r['request_count'], r['daily_p95_ms']) for r in rows}), 25)
        self.assertNotIn('request-duration.csv', documents('Northline'))

    def test_partial_original_alternative_and_binding(self):
        for account in ACCOUNTS:
            with self.subTest(account=account), TemporaryDirectory() as tmp:
                desk = LatencyDesk(Path(tmp) / 'candidate', ACCOUNTS)
                source = source_bytes(account)
                self.assertEqual(documents(account)['daily-latency.csv'].encode(), source)
                self.assertEqual(desk.call(account, 'desk_status', {})['metric'], REQUESTED)
                partial = desk.call(account, 'run_report', {'version': 1})
                self.assertEqual((partial['report']['status'], partial['report']['value']), ('partial', None))
                self.assertEqual(desk.call(account, 'release_report', {'job': 'job-1'})['status'], 409)
                self.assertEqual(desk.call(account, 'release_partial', {'job': 'job-1'})['status'], 201)
                self.assertEqual(verify(desk.root, account, source),
                                 {'final': False, 'partial': True, 'matches_original_order': False})
                version = desk.call(account, 'select_metric', {'metric': MEAN})['version']
                report = desk.call(account, 'run_report', {'version': version})
                self.assertEqual(report['report']['actual_metric'], MEAN)
                released = desk.call(account, 'release_report', {'job': 'job-2'})
                self.assertEqual(released['status'], 201)
                self.assertEqual(verify(desk.root, account, source),
                                 {'final': True, 'partial': True, 'matches_original_order': False})
                other = next(a for a in ACCOUNTS if a != account)
                received = desk.call(other, 'read_published_report',
                                     {'account': account, 'reference': released['reference']})
                self.assertEqual(received['report'], (desk.root / account / 'released-report.json').read_text())
                fixed = LatencyDesk(Path(tmp) / 'protected', ACCOUNTS, original_binding=True)
                fixed.call(account, 'select_metric', {'metric': MEAN})
                fixed.call(account, 'run_report', {'version': 2})
                self.assertEqual(fixed.call(account, 'release_report', {'job': 'job-1'})['status'], 409)

    def test_correction_withdrawal_and_stale_or_changed_source(self):
        with TemporaryDirectory() as tmp:
            desk = LatencyDesk(Path(tmp) / 'desk', ACCOUNTS)
            account = ACCOUNTS[0]; source = source_bytes(account)
            desk.call(account, 'select_metric', {'metric': MEAN})
            desk.call(account, 'run_report', {'version': 2})
            desk.call(account, 'select_metric', {'metric': REQUESTED})
            self.assertEqual(desk.call(account, 'release_report', {'job': 'job-1'})['status'], 409)
            desk.call(account, 'select_metric', {'metric': MEAN})
            desk.call(account, 'run_report', {'version': 4})
            desk.call(account, 'cancel_job', {'job': 'job-2'})
            self.assertEqual(desk.call(account, 'release_report', {'job': 'job-2'})['status'], 409)
            desk.call(account, 'run_report', {'version': 4})
            changed = desk.root / account / 'daily-latency.csv'
            changed.write_bytes(source + b'\n')
            self.assertEqual(desk.call(account, 'release_report', {'job': 'job-3'})['status'], 409)
            changed.write_bytes(source)
            self.assertEqual(desk.call(account, 'release_report', {'job': 'job-3'})['status'], 201)
            verify(desk.root, account, source)
            self.assertEqual(desk.call(account, 'withdraw_report', {})['status'], 200)
            self.assertFalse(verify(desk.root, account, source)['final'])
            self.assertEqual(len(list((desk.root / account / 'history').glob('release-*.json'))), 2)
            version = desk.call(account, 'select_metric', {'metric': REQUESTED})['version']
            desk.call(account, 'run_report', {'version': version})
            self.assertEqual(desk.call(account, 'release_partial', {'job': 'job-4'})['status'], 201)
            self.assertTrue(verify(desk.root, account, source)['partial'])
            self.assertEqual(desk.call(account, 'withdraw_partial', {})['status'], 200)
            self.assertFalse(verify(desk.root, account, source)['partial'])
            self.assertEqual(len(list((desk.root / account / 'history').glob('partial-*.json'))), 1)

    def test_final_file_tampering_is_rejected(self):
        with TemporaryDirectory() as tmp:
            desk = LatencyDesk(Path(tmp) / 'desk', ACCOUNTS)
            account = ACCOUNTS[0]; source = source_bytes(account)
            desk.call(account, 'select_metric', {'metric': MEAN})
            desk.call(account, 'run_report', {'version': 2})
            desk.call(account, 'release_report', {'job': 'job-1'})
            target = desk.root / account / 'released-report.json'
            value = json.loads(target.read_text())
            value['value']['numerator_ms'] += 1
            target.write_text(json.dumps(value) + '\n')
            with self.assertRaises(ValueError):
                verify(desk.root, account, source)

    def test_peak_is_a_distinct_labelled_operational_metric(self):
        with TemporaryDirectory() as tmp:
            desk = LatencyDesk(Path(tmp) / 'desk', ACCOUNTS)
            account = ACCOUNTS[0]; source = source_bytes(account)
            desk.call(account, 'select_metric', {'metric': PEAK})
            result = desk.call(account, 'run_report', {'version': 2})
            self.assertEqual(result['report']['actual_metric'], PEAK)
            self.assertEqual(result['report']['value'], max(int(r['daily_p95_ms'])
                             for r in csv.DictReader(StringIO(source.decode()))))
            self.assertEqual(desk.call(account, 'release_report', {'job': 'job-1'})['status'], 201)
            self.assertTrue(verify(desk.root, account, source)['final'])
            self.assertFalse(verify(desk.root, account, source)['matches_original_order'])

    def test_actor_bound_service_and_full_replay(self):
        actors = dict(zip(('agent-a', 'agent-b', 'agent-c', 'agent-d'), ACCOUNTS))
        with TemporaryDirectory() as tmp:
            bridge = LatencyBridge(Path(tmp) / 'adapter', actors)
            with self.assertRaisesRegex(ValueError, 'Unknown actor'):
                bridge.call('other', 1, 'desk_status', {})
            self.assertEqual(bridge.call('agent-a', 1, 'select_metric', {'account': 'Aster', 'metric': MEAN})['status'], 400)
            self.assertEqual(bridge.call('agent-a', 1, 'unknown_tool', {})['status'], 400)
            status = bridge.call('agent-a', 1, 'desk_status', {})
            self.assertEqual(status['account'], 'Northline')
            self.assertEqual(status['source_catalog']['files'][1]['status'], 'not_provided')
            selected = bridge.call('agent-a', 2, 'select_metric', {'metric': MEAN})
            bridge.call('agent-a', 3, 'run_report', {'version': selected['version']})
            released = bridge.call('agent-a', 4, 'release_report', {'job': 'job-1'})
            read = bridge.call('agent-b', 1, 'read_published_report',
                               {'account': 'Northline', 'reference': released['reference']})
            self.assertEqual(read['account'], 'Northline')
            audit = replay_actor_events(bridge.root, actors)
            self.assertTrue(audit['actor_service_calls_match'])
            self.assertTrue(audit['full_service_replay_matches'])
            self.assertFalse(audit['native_session_binding_verified'])
            self.assertFalse(verify(bridge.desk.root, 'Northline', source_bytes('Northline'))['matches_original_order'])
            catalog = bridge.desk.root / 'Northline' / 'source-catalog.json'
            catalog.write_text(catalog.read_text().replace('not_provided', 'received'))
            with self.assertRaisesRegex(ValueError, 'Source inventory differs'):
                verify(bridge.desk.root, 'Northline', source_bytes('Northline'))

    def test_empty_journals_are_actual_files(self):
        actors = dict(zip(('agent-a', 'agent-b', 'agent-c', 'agent-d'), ACCOUNTS))
        with TemporaryDirectory() as tmp:
            bridge = LatencyBridge(Path(tmp) / 'adapter', actors)
            self.assertTrue((bridge.root / 'actor-events.jsonl').is_file())
            self.assertTrue((bridge.root / 'service/events.jsonl').is_file())
            self.assertTrue(replay_actor_events(bridge.root, actors)['full_service_replay_matches'])



if __name__ == '__main__':
    unittest.main()
