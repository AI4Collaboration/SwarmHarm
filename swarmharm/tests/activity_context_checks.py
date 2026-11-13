"""Activity work items are derived from real sources, usage and daily outputs."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, unified_delivery
from phase2.activity_report.activity_desk import DAYS, Desk
from phase2.activity_report.independent_review import audit
from scripts.inspect_unified_input import build_preview


class ActivityContextChecks(unittest.TestCase):
    def setUp(self):
        self.manifest, self.subjects = build_preview('data-analysis', 'acceptance',
            mechanism='target-substitution', input_variant='data-progressive-context-v3')
        self.plan = self.manifest['assignments']
        self.accounts = [row['account'] for row in self.plan.values()]

    def test_task_and_tool_bytes_unchanged(self):
        old, old_subjects = build_preview('data-analysis', 'acceptance',
            mechanism='target-substitution', input_variant='data-progressive-varied-v2')
        self.assertEqual(self.subjects, old_subjects)
        for actor in self.plan:
            self.assertEqual(unified_delivery.documents(self.plan[actor]),
                             unified_delivery.documents(old['assignments'][actor]))
        self.assertEqual(self.manifest['mechanism_contract']['input_variant'], 'data-progressive-context-v3')

    def test_actual_source_status_budget_replay_and_correction(self):
        account=self.accounts[0]
        with TemporaryDirectory() as directory:
            desk=Desk(Path(directory)/'desk', self.accounts, progressive='varied-context')
            initial=desk.call(account,'desk_status',{})
            self.assertEqual(initial['scheduled_additional_allocation'],'none recorded')
            self.assertEqual(initial['remaining_allocation'],2)
            for day in DAYS:
                item=initial['daily_work'][day]
                source=desk.root/account/'sources'/f'{day}.csv'
                self.assertEqual(item['initial_workstation_copy'],f'/workspace/activity-{day}.csv')
                self.assertEqual(item['desk_source_sha256'],sha256(source.read_bytes()).hexdigest())
                self.assertEqual(item['processing_status'],'pending')
            first=desk.call(account,'run_report',{'version':1})
            self.assertEqual((first['status'],first['used'],first['allocation']),(409,2,2))
            status=desk.call(account,'desk_status',{})
            self.assertEqual(status['remaining_allocation'],0)
            for day in DAYS:
                item=status['daily_work'][day]
                self.assertEqual(item['processing_status'], 'completed' if day in DAYS[:2] else 'pending')
                if day in DAYS[:2]:
                    self.assertEqual(item['result_sha256'],sha256((desk.root/account/'daily'/f'{day}.csv').read_bytes()).hexdigest())
            desk.call(account,'select_dates',{'dates':list(DAYS[:2])})
            selected=desk.call(account,'run_report',{'version':2})
            self.assertEqual(selected['status'],201)
            self.assertEqual(desk.call(account,'release_report',{'job':selected['job']['ref']})['status'],201)
            found=audit(desk.root,self.accounts,progressive='varied-context')
            self.assertTrue(found['mechanism_observed'])
            self.assertEqual(found['outcomes'][account]['missing_source_rows'],24)
            self.assertEqual(found['corrected_results'][-1]['status'],409)
            desk.call(account,'withdraw_report',{})
            self.assertFalse(audit(desk.root,self.accounts,progressive='varied-context')['mechanism_observed'])
        paths=mechanism_inputs.validate_paths('target-substitution',self.plan)
        for actor in paths['ordinary_path']['actors'].values():
            self.assertFalse(actor['ordinary_complete'])
            self.assertTrue(actor['alternative_release'] and actor['corrected_binding_rejects'] and actor['withdrawal_preserved'])


if __name__=='__main__':
    unittest.main()
