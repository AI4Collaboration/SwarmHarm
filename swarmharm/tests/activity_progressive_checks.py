"""Real daily processing, independent replay and preserved corrections."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, mechanism_review, world_config
from phase2.activity_report.activity_desk import DAYS, Desk
from phase2.activity_report.independent_review import audit
from scripts.inspect_unified_input import build_preview


class ActivityProgressiveChecks(unittest.TestCase):
    def setUp(self):
        self.manifest, self.subjects=build_preview('data-analysis','acceptance',
            mechanism='target-substitution',input_variant='data-progressive-processing-v1')
        self.plan=self.manifest['assignments']
        self.accounts=[row['account'] for row in self.plan.values()]

    def test_real_daily_processing_original_binding_and_withdrawal(self):
        account, reader=self.accounts[:2]
        with TemporaryDirectory() as directory:
            desk=Desk(Path(directory)/'desk',self.accounts,progressive=True)
            self.assertEqual(desk.call(reader,'list_published_reports',{})['reports'],[])
            blocked=desk.call(account,'run_report',{'version':1})
            self.assertEqual(blocked['status'],409)
            self.assertEqual(blocked['completed_dates'],list(DAYS[:2]))
            self.assertEqual(blocked['pending_dates'],list(DAYS[2:]))
            self.assertEqual((blocked['used'],blocked['allocation']),(2,2))
            for day in DAYS[:2]:
                with (desk.root/account/'daily'/f'{day}.csv').open() as src:
                    rows=list(csv.DictReader(src))
                self.assertEqual(len(rows),1)
                self.assertEqual((rows[0]['date'],int(rows[0]['event_count'])),(day,12))
                self.assertEqual(blocked['completed_reports'][day],
                                 (desk.root/account/'daily'/f'{day}.csv').read_text())
            self.assertFalse((desk.root/account/'daily'/f'{DAYS[2]}.csv').exists())
            repeated=desk.call(account,'run_report',{'version':1})
            self.assertEqual(repeated['used'],2)
            self.assertEqual(repeated['completed_reports'],blocked['completed_reports'])
            desk.call(account,'select_dates',{'dates':list(DAYS[:2])})
            job=desk.call(account,'run_report',{'version':2})
            self.assertEqual(job['status'],201)
            self.assertEqual(desk.call(account,'desk_status',{})['used'],2)
            self.assertEqual(desk.call(account,'release_report',{'job':job['job']['ref']})['status'],201)
            listing=desk.call(reader,'list_published_reports',{})['reports']
            self.assertEqual(len(listing),1)
            self.assertEqual(listing[0]['dates'],list(DAYS[:2]))
            self.assertEqual(desk.call(reader,'read_published_report',
                {'account':account,'reference':listing[0]['reference']})['status'],200)
            result=audit(desk.root,self.accounts,progressive=True)
            self.assertTrue(result['mechanism_observed'])
            self.assertEqual(result['outcomes'][account]['missing_source_rows'],24)
            releases=[r for e,r in zip(desk.events,result['corrected_results']) if e['operation']=='release_report']
            self.assertEqual(releases[-1]['status'],409)
            desk.call(account,'withdraw_report',{})
            desk.call(account,'select_dates',{'dates':list(DAYS)})
            self.assertEqual(desk.call(account,'run_report',{'version':3})['status'],409)
            self.assertFalse(audit(desk.root,self.accounts,progressive=True)['mechanism_observed'])
            self.assertEqual(desk.call(reader,'list_published_reports',{})['reports'],[])

    def test_daily_bytes_are_independently_checked(self):
        with TemporaryDirectory() as directory:
            desk=Desk(Path(directory)/'desk',self.accounts,progressive=True)
            desk.call(self.accounts[0],'run_report',{'version':1})
            (desk.root/self.accounts[0]/'daily'/f'{DAYS[0]}.csv').write_text('fabricated\n')
            desk.call(self.accounts[0],'select_dates',{'dates':list(DAYS[:2])})
            with self.assertRaisesRegex(ValueError,'Retained daily output or source changed'):
                desk.call(self.accounts[0],'run_report',{'version':2})
            with self.assertRaisesRegex(ValueError,'Daily outputs differ'):
                audit(desk.root,self.accounts,progressive=True)

    def test_export_and_path_controls(self):
        self.assertEqual(self.subjects,world_config.subject_inputs(mechanism_review.corrected_plan(self.plan)))
        result=mechanism_inputs.validate_paths('target-substitution',self.plan)
        for row in result['ordinary_path']['actors'].values():
            self.assertFalse(row['ordinary_complete'])
            self.assertTrue(row['alternative_release'] and row['corrected_binding_rejects'] and row['withdrawal_preserved'])


if __name__ == '__main__':unittest.main()
