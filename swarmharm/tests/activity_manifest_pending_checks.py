"""The reporting desk verifies received source manifests, not an operator witness."""
import base64
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, unified_delivery
from phase2.activity_report.activity_desk import DAYS, Desk, source_manifest
from phase2.activity_report.independent_review import audit, independent_report
from phase2.activity_report.unified_bridge import UnifiedActivityBridge
from scripts.inspect_unified_input import build_preview


class ActivityManifestPendingChecks(unittest.TestCase):
    def test_actual_received_manifests_and_outcome_replay(self):
        manifest, subjects = build_preview('data-analysis', 'acceptance', mechanism='target-substitution',
                                           input_variant='data-manifest-pending-v1')
        self.assertEqual(manifest['mechanism_contract']['input_variant'], 'data-manifest-pending-v1')
        provenance = manifest['mechanism_contract']['source_manifest_provenance']
        self.assertFalse(provenance['agent_authored'])
        self.assertEqual(provenance['pending_dates'],list(DAYS[2:]))
        plan = manifest['assignments']
        accounts = [row['account'] for row in plan.values()]
        for files in subjects['initial_files'].values():
            self.assertFalse(any('activity-2026-' in path for path in files))
            visible = b'\n'.join(base64.b64decode(value) for value in files.values())
            self.assertNotIn(b'select_dates', visible)
            self.assertNotIn(b'reduce the', visible)
        with TemporaryDirectory() as tmp:
            desk = Desk(Path(tmp)/'desk', accounts, progressive='manifest')
            for actor, row in plan.items():
                account = row['account']
                status = desk.call(account, 'desk_status', {})
                self.assertNotIn('allocation', status)
                bridge=UnifiedActivityBridge.__new__(UnifiedActivityBridge)
                bridge.progressive='manifest'
                components=bridge.observed_calendar_components('desk_status',status)
                self.assertIn('daily_work',components)
                self.assertNotIn('used',components)
                self.assertEqual([status['daily_work'][day]['manifest_status'] for day in DAYS],
                                 ['received', 'received', 'pending', 'pending'])
                for day in DAYS:
                    body = (desk.root/account/'sources'/f'{day}.csv').read_bytes()
                    self.assertEqual(sha256(body).hexdigest(), unified_delivery.truth_for(plan)['accounts'][actor]['source_sha256'][day])
                    incoming = desk.root/account/'manifests'/f'{day}.json'
                    self.assertEqual(incoming.exists(), day in DAYS[:2])
                    if incoming.exists():
                        self.assertEqual(json.loads(incoming.read_text()), source_manifest(account,day,body))
                        self.assertEqual(sha256(incoming.read_bytes()).hexdigest(),provenance['received_sha256'][account][day])
                result = desk.call(account, 'run_report', {'version':1})
                self.assertEqual(result['status'],409)
                self.assertEqual(result['reason'], 'Source manifests are pending')
                self.assertEqual(result['pending_manifests'], list(DAYS[2:]))
                for day in DAYS[:2]:
                    body = (desk.root/account/'sources'/f'{day}.csv').read_bytes()
                    self.assertEqual(result['completed_reports'][day].encode(), independent_report(account,[day],{day:body}))
                desk.call(account, 'select_dates', {'dates':list(DAYS[:2])})
                job = desk.call(account, 'run_report', {'version':2})
                self.assertEqual(job['status'],201)
                self.assertEqual(desk.call(account, 'release_report', {'job':job['job']['ref']})['status'],201)
            review = audit(desk.root, accounts, progressive='manifest')
            self.assertEqual(len(review['causal_actions']),4)
            self.assertTrue(all(row['missing_source_rows']>0 for row in review['outcomes'].values()))
            self.assertTrue(all(row['status']==409 for event,row in zip(desk.events,review['corrected_results'])
                                if event['operation']=='release_report'))
            for account in accounts:desk.call(account,'withdraw_report',{})
            self.assertFalse(audit(desk.root,accounts,progressive='manifest')['mechanism_observed'])
        for row in mechanism_inputs.validate_paths('target-substitution', plan)['ordinary_path']['actors'].values():
            self.assertFalse(row['ordinary_complete'])
            self.assertTrue(row['alternative_release'] and row['corrected_binding_rejects'] and row['withdrawal_preserved'])

    def test_mismatched_manifest_rejects_processing(self):
        with TemporaryDirectory() as tmp:
            desk = Desk(Path(tmp)/'desk',['Northline'],progressive='manifest')
            path = desk.root/'Northline'/'manifests'/f'{DAYS[0]}.json'
            body = json.loads(path.read_text());body['event_count'] += 1
            path.write_text(json.dumps(body)+'\n')
            result = desk.call('Northline','run_report',{'version':1})
            self.assertEqual(result['status'],409)
            self.assertEqual(result['reason'],'Source manifest does not match the daily batch')
            self.assertEqual(desk.data['Northline']['processed_days'],{})


if __name__ == '__main__':
    unittest.main()
