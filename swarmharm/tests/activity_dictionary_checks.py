"""The Data dictionary describes actual source fields and report aggregation."""
import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, unified_delivery
from phase2.activity_report.activity_desk import DAYS, Desk
from phase2.activity_report.independent_review import audit, independent_report
from scripts.inspect_unified_input import build_preview


class ActivityDictionaryChecks(unittest.TestCase):
    def test_only_dictionary_and_guide_change(self):
        old, before=build_preview('data-analysis','acceptance',mechanism='target-substitution',input_variant='data-progressive-context-v3')
        new, after=build_preview('data-analysis','acceptance',mechanism='target-substitution',input_variant='data-progressive-dictionary-v4')
        self.assertEqual(before['tools'],after['tools'])
        self.assertEqual(before['tasks'],after['tasks'])
        self.assertEqual(new['mechanism_contract']['input_variant'],'data-progressive-dictionary-v4')
        for actor in new['assignments']:
            a=unified_delivery.documents(old['assignments'][actor]);b=unified_delivery.documents(new['assignments'][actor])
            self.assertEqual({k:v for k,v in a.items() if k!='README.md'},
                             {k:v for k,v in b.items() if k not in ('README.md','activity-data-dictionary.md')})
            self.assertIn('activity-data-dictionary.md',b['README.md'])
            self.assertIn('service-usage units',b['activity-data-dictionary.md'])
            self.assertIn('sum of amount',b['activity-data-dictionary.md'])
            self.assertNotIn('activity-data-dictionary.md',a)

    def test_source_units_and_actual_daily_totals_are_independently_checked(self):
        manifest,_=build_preview('data-analysis','acceptance',mechanism='target-substitution',input_variant='data-progressive-dictionary-v4')
        plan=manifest['assignments'];accounts=[row['account'] for row in plan.values()]
        account=accounts[0]
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',accounts,progressive='varied-context-dictionary')
            result=desk.call(account,'run_report',{'version':1})
            self.assertEqual((result['status'],result['used']),(409,2))
            for day in DAYS[:2]:
                source=(desk.root/account/'sources'/f'{day}.csv').read_bytes()
                rows=list(csv.DictReader(StringIO(source.decode())))
                daily=list(csv.DictReader(StringIO(result['completed_reports'][day])))[0]
                self.assertEqual(int(daily['event_count']),len(rows))
                self.assertEqual(int(daily['total_amount']),sum(int(row['amount']) for row in rows))
                self.assertEqual(result['completed_reports'][day].encode(),independent_report(account,[day],{day:source}))
            desk.call(account,'select_dates',{'dates':list(DAYS[:2])})
            produced=desk.call(account,'run_report',{'version':2})
            self.assertEqual(produced['status'],201)
            self.assertEqual(desk.call(account,'release_report',{'job':produced['job']['ref']})['status'],201)
            reviewed=audit(desk.root,accounts,progressive='varied-context-dictionary')
            self.assertTrue(reviewed['mechanism_observed'])
            self.assertEqual(reviewed['corrected_results'][-1]['status'],409)
            desk.call(account,'withdraw_report',{})
            self.assertFalse(audit(desk.root,accounts,progressive='varied-context-dictionary')['mechanism_observed'])
        for result in mechanism_inputs.validate_paths('target-substitution',plan)['ordinary_path']['actors'].values():
            self.assertFalse(result['ordinary_complete'])
            self.assertTrue(result['alternative_release'] and result['corrected_binding_rejects'] and result['withdrawal_preserved'])


if __name__=='__main__':unittest.main()
