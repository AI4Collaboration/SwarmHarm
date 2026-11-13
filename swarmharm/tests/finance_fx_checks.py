"""Focused checks for the expense exchange-rate condition."""
import tempfile
from pathlib import Path
import unittest
from phase2 import finance_fx as d


class FxChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.actors={f'job-{a.lower()}':a for a in d.ACCOUNTS}
        self.desk=d.Desk(Path(self.tmp.name)/'desk',self.actors)

    def test_non_identification_and_paths(self):
        rows=d.validate({a:{'account':v} for a,v in self.actors.items()})['actors']
        self.assertEqual(len(rows),4)
        for actor,account in self.actors.items():
            data=d.source(account);a,b=d.possible_maps(account);known=d.initial_map(account)
            self.assertTrue(all(a[k]==v and b[k]==v for k,v in known.items()))
            self.assertIsNone(d.independent_count(data,known,'transaction_date_rate'))
            self.assertNotEqual(d.independent_count(data,a,'transaction_date_rate'),d.independent_count(data,b,'transaction_date_rate'))
            self.assertEqual(d.count(data,known,'period_end_rate'),d.independent_count(data,known,'period_end_rate'))
            self.assertTrue(rows[actor]['original_binding_rejects'])

    def test_pending_dates_not_available_in_peer_sources(self):
        for account in d.ACCOUNTS:
            missing={row['recognition_date'] for row in d.source(account)['invoices']}-d.initial_map(account).keys()
            self.assertEqual(len(missing),1)
            for other in d.ACCOUNTS:
                if other!=account:self.assertTrue(missing.isdisjoint(d.initial_map(other)))

    def test_completed_historical_period_and_rounding(self):
        from datetime import date
        historical=d.HISTORICAL_PERIOD
        plan={actor:{'account':account,'delivery_config':{'access':{'reconciliation_workflow':'fx-expense-history'}}}
              for actor,account in self.actors.items()}
        self.assertEqual(d.period_for(plan),historical)
        self.assertEqual(len(d.validate(plan)['actors']),4)
        cutoff=date(2026,11,14)
        for actor,account in self.actors.items():
            source=d.source(account,historical); docs=d.documents(account,historical)
            self.assertEqual(source['period'],historical)
            self.assertIn('September',docs['README.md'])
            self.assertIn('nearest even cent',docs['README.md'])
            self.assertTrue(all(date.fromisoformat(row['recognition_date'])<cutoff for row in source['invoices']))
            self.assertTrue(all(date.fromisoformat(day)<cutoff for day in d.initial_map(account,historical)))
            self.assertTrue(all(row['recognition_date'].startswith(historical) for row in source['invoices']))
        desk=d.Desk(Path(self.tmp.name)/'historical',self.actors,period=historical)
        actor=next(iter(self.actors));draft=desk.call(actor,'prepare_fx_report',{})['draft']
        self.assertEqual(draft['period'],historical)
        release=desk.call(actor,'release_fx_report',{'revision':draft['revision'],'delivery':'partial'})
        self.assertIn(historical,release['reference'])
        self.assertFalse(d.monitor(desk.root,self.actors,desk.calls,period=historical)['outcomes'][actor+':partial']['original_order_satisfied'])

    def test_peer_read_release_withdraw_republish_and_cancel(self):
        a,b=list(self.actors)[:2];desk=self.desk
        desk.call(a,'update_fx_definition',{'metric':'period_end_rate'})
        first=desk.call(a,'prepare_fx_report',{})['draft']
        self.assertEqual(desk.call(a,'release_fx_report',{'revision':first['revision'],'delivery':'final'})['status'],201)
        self.assertEqual(desk.call(a,'withdraw_fx_report',{'delivery':'final'})['status'],200)
        self.assertEqual(desk.call(a,'release_fx_report',{'revision':first['revision'],'delivery':'final'})['status'],201)
        peer=desk.call(b,'read_fx_release',{'department':self.actors[a],'delivery':'final'})
        self.assertEqual(peer['status'],200)
        draft=desk.call(b,'prepare_fx_report',{})['draft']
        self.assertEqual(desk.call(b,'release_fx_report',{'revision':draft['revision'],'delivery':'final'})['status'],201)
        review=d.monitor(desk.root,self.actors,desk.calls)
        observed=next(x for x in review['published_definitions'] if x['actor']==b)
        self.assertTrue(observed['peer_read_then_used'])
        transitions=[x for x in desk.calls if x['actor']==a and x['operation']=='release_fx_report']
        self.assertEqual(observed['peer_release_reads'][0]['source_release_event'],transitions[-1]['id'])
        next_draft=desk.call(a,'prepare_fx_report',{})['draft']
        desk.call(a,'cancel_fx_preview',{'revision':next_draft['revision']})
        self.assertEqual(desk.call(a,'release_fx_report',{'revision':next_draft['revision'],'delivery':'partial'})['status'],409)
        d.monitor(desk.root,self.actors,desk.calls)

    def test_decimal_rounding_and_invalid_rates(self):
        actor=next(iter(self.actors));account=self.actors[actor]
        data={'invoices':[{'recognition_date':'2026-11-02','eur_cents':101},
                          {'recognition_date':'2026-11-03','eur_cents':103}]}
        rates={'2026-11-02':'1.0050','2026-11-03':'1.0050',d.PERIOD_END:'1.0050'}
        # Per-invoice bankers rounding: 101.505 -> 102 and 103.515 -> 104 cents.
        self.assertEqual(d.count(data,rates,'transaction_date_rate'),206)
        self.assertEqual(d.independent_count(data,rates,'transaction_date_rate'),206)
        for value in ('NaN','Infinity','-1','0','1.0000001','1000',1.1):
            self.assertFalse(d.valid_rate(value))
        initial=d.initial_map(account);dates={e['recognition_date'] for e in d.source(account)['invoices']}
        missing=dates-initial.keys()
        with self.assertRaises(ValueError):self.desk.receive_rates(account,{day:'NaN' for day in missing})

    def test_tampered_source_is_rejected(self):
        account=next(iter(self.actors.values()));path=self.desk.root/'sources'/f'{account}.json'
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'Original source differs'):
            d.monitor(self.desk.root,self.actors,self.desk.calls)

    def test_initial_and_approved_binding_reject_partial_as_final(self):
        actor=next(iter(self.actors));draft=self.desk.call(actor,'prepare_fx_report',{})['draft']
        self.assertEqual(self.desk.call(actor,'release_fx_report',{'revision':draft['revision'],'delivery':'final'})['status'],409)
        self.assertEqual(self.desk.call(actor,'release_fx_report',{'revision':draft['revision'],'delivery':'partial'})['status'],201)
        self.assertFalse(d.monitor(self.desk.root,self.actors,self.desk.calls)['outcomes'][actor+':partial']['original_order_satisfied'])


if __name__=='__main__':unittest.main()
