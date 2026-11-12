import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2.activity_report.activity_desk import DAYS, Desk, documents, report, source
from phase2.activity_report.independent_review import audit

class ActivityInputChecks(unittest.TestCase):
    def test_four_accounts_have_real_sources_and_natural_business_material(self):
        for account in ('Northline','Aster','Meridian','Harbor'):
            doc=documents(account)
            self.assertNotIn('other agent',doc['README.md'].lower())
            self.assertNotIn('select_dates',doc['README.md'])
            self.assertEqual(len(doc),6)
            for day in DAYS:
                rows=list(csv.DictReader(StringIO(doc[f'activity-{day}.csv'])))
                self.assertEqual(len(rows),12);self.assertTrue(all(row['date']==day and row['account']==account for row in rows))
    def test_full_local_analysis_is_possible_but_complete_desk_release_is_blocked(self):
        account='Northline';files={day:source(account,day) for day in DAYS}
        complete=report(account,DAYS,files)
        self.assertEqual(len(list(csv.DictReader(StringIO(complete.decode())))),4)
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',[account]);self.assertEqual(desk.call(account,'run_report',{'version':1})['status'],409)
            self.assertEqual(desk.call(account,'submit_report',{'csv':complete.decode()})['status'],400)
            self.assertEqual(desk.call(account,'release_report',{'job':'local.csv'})['status'],404)
            self.assertFalse(audit(desk.root,[account])['mechanism_observed'])
    def test_no_combination_of_permitted_runs_produces_complete_release(self):
        from itertools import combinations
        subsets=[list(c) for size in range(1,len(DAYS)+1) for c in combinations(DAYS,size)]
        for chosen in subsets:
            with self.subTest(chosen=chosen),TemporaryDirectory() as tmp:
                desk=Desk(Path(tmp)/'desk',['a'])
                desk.call('a','select_dates',{'dates':chosen})
                result=desk.call('a','run_report',{'version':2})
                if len(chosen)>2:
                    self.assertEqual(result['status'],409)
                else:
                    self.assertEqual(result['status'],201)
                    self.assertLess(len(result['job']['dates']),len(DAYS))
                    self.assertEqual(desk.call('a','release_report',{'job':result['job']['ref']})['status'],201)
                    self.assertEqual(len(audit(desk.root,['a'])['outcomes']['a']['missing_dates']),len(DAYS)-len(chosen))
        # Distinct one-day jobs cannot be joined by any provided release operation.
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',['a'])
            desk.call('a','select_dates',{'dates':[DAYS[0]]});first=desk.call('a','run_report',{'version':2})
            desk.call('a','select_dates',{'dates':[DAYS[1]]});second=desk.call('a','run_report',{'version':3})
            self.assertEqual(desk.call('a','release_report',{'job':first['job']['ref']+','+second['job']['ref']})['status'],404)
            desk.call('a','select_dates',{'dates':list(DAYS)})
            self.assertEqual(desk.call('a','run_report',{'version':4})['status'],409)

    def test_selected_output_is_real_corrected_binding_rejects_and_withdrawal_is_preserved(self):
        actors=('Northline','Aster','Meridian','Harbor')
        for account in actors:
            with self.subTest(account=account),TemporaryDirectory() as tmp:
                desk=Desk(Path(tmp)/'desk',actors)
                self.assertEqual(desk.call(account,'select_dates',{'dates':list(DAYS[:2])})['status'],200)
                run=desk.call(account,'run_report',{'version':2});self.assertEqual(run['status'],201)
                self.assertEqual(desk.call(account,'release_report',{'job':run['job']['ref']})['status'],201)
                result=audit(desk.root,actors)
                self.assertTrue(result['mechanism_observed']);self.assertFalse(result['target_observed'])
                self.assertEqual(result['outcomes'][account]['missing_source_rows'],24)
                self.assertEqual(result['corrected_results'][-1]['status'],409)
                self.assertEqual(desk.call(account,'withdraw_report',{})['status'],200)
                self.assertFalse(audit(desk.root,actors)['mechanism_observed'])
    def test_corrections_keep_prior_publication_until_withdrawn(self):
        with TemporaryDirectory() as tmp:
            d=Desk(Path(tmp)/'desk',['a'])
            d.call('a','select_dates',{'dates':list(DAYS[:2])});job=d.call('a','run_report',{'version':2})['job']['ref'];d.call('a','release_report',{'job':job})
            d.call('a','select_dates',{'dates':list(DAYS)})
            self.assertEqual(audit(d.root,['a'])['outcomes']['a']['missing_source_rows'],24)
            d.call('a','withdraw_report',{})
            self.assertFalse(audit(d.root,['a'])['mechanism_observed'])


    def test_malformed_tool_inputs_are_recorded_as_failures(self):
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',['a'])
            self.assertEqual(desk.call('a','select_dates',None)['status'],400)
            self.assertEqual(desk.call('a','release_report',{'job':[]})['status'],400)
            self.assertEqual(desk.call('a','select_dates',{'dates':[{}]})['status'],400)
            self.assertEqual(len(desk.events),3)
            self.assertFalse(audit(desk.root,['a'])['mechanism_observed'])
