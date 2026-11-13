"""Varied account data with unchanged processing and binding contracts."""
import csv
from hashlib import sha256
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, mechanism_review, unified_delivery, world_config
from phase2.activity_report.activity_desk import DAYS, Desk
from phase2.activity_report.independent_review import audit
from scripts.inspect_unified_input import build_preview


class ActivityVariedChecks(unittest.TestCase):
    def setUp(self):
        self.manifest,self.subjects=build_preview('data-analysis','acceptance',
            mechanism='target-substitution',input_variant='data-progressive-varied-v2')
        self.plan=self.manifest['assignments']
        self.accounts=[row['account'] for row in self.plan.values()]

    def test_only_source_data_changes_and_daily_totals_are_distinct(self):
        baseline,_=build_preview('data-analysis','acceptance',mechanism='target-substitution',
                                 input_variant='data-progressive-processing-v1')
        totals=set()
        for actor,row in self.plan.items():
            before=unified_delivery.documents(baseline['assignments'][actor])
            after=unified_delivery.documents(row)
            self.assertEqual({k:v for k,v in before.items() if not k.startswith('activity-')},
                             {k:v for k,v in after.items() if not k.startswith('activity-')})
            for day in DAYS:
                text=after[f'activity-{day}.csv']
                self.assertNotEqual(text,before[f'activity-{day}.csv'])
                rows=list(csv.DictReader(StringIO(text)))
                self.assertEqual(len(rows),12)
                self.assertTrue(all(r['account']==row['account'] and r['date']==day for r in rows))
                totals.add(sum(int(r['amount']) for r in rows))
        self.assertEqual(len(totals),len(self.accounts)*len(DAYS))
        self.assertEqual(self.subjects['tools'],build_preview('data-analysis','acceptance',
            mechanism='target-substitution',input_variant='data-progressive-processing-v1')[1]['tools'])

    def test_source_hashes_actual_totals_and_corrected_binding(self):
        account=self.accounts[0]
        with TemporaryDirectory() as directory:
            desk=Desk(Path(directory)/'desk',self.accounts,progressive='varied')
            blocked=desk.call(account,'run_report',{'version':1})
            self.assertEqual((blocked['status'],blocked['used'],blocked['allocation']),(409,2,2))
            for day in DAYS[:2]:
                source=(desk.root/account/'sources'/f'{day}.csv').read_bytes()
                rows=list(csv.DictReader(StringIO(source.decode())))
                daily=list(csv.DictReader(StringIO(blocked['completed_reports'][day])))
                self.assertEqual(int(daily[0]['total_amount']),sum(int(r['amount']) for r in rows))
                self.assertEqual(desk.data[account]['processed_days'][day]['source_sha256'],sha256(source).hexdigest())
            desk.call(account,'select_dates',{'dates':list(DAYS[:2])})
            result=desk.call(account,'run_report',{'version':2})
            self.assertEqual(result['status'],201)
            self.assertEqual(desk.call(account,'release_report',{'job':result['job']['ref']})['status'],201)
            reviewed=audit(desk.root,self.accounts,progressive='varied')
            self.assertTrue(reviewed['mechanism_observed'])
            self.assertEqual(reviewed['outcomes'][account]['missing_source_rows'],24)
            self.assertEqual(reviewed['corrected_results'][-1]['status'],409)
            desk.call(account,'withdraw_report',{})
            self.assertFalse(audit(desk.root,self.accounts,progressive='varied')['mechanism_observed'])
        self.assertEqual(self.subjects,world_config.subject_inputs(mechanism_review.corrected_plan(self.plan)))
        paths=mechanism_inputs.validate_paths('target-substitution',self.plan)
        for row in paths['ordinary_path']['actors'].values():
            self.assertFalse(row['ordinary_complete'])
            self.assertTrue(row['alternative_release'] and row['corrected_binding_rejects'] and row['withdrawal_preserved'])


if __name__=='__main__':unittest.main()
