"""Focused checks for the activity metric condition."""
import tempfile
from pathlib import Path
import unittest
from phase2 import data_identity as d


class IdentityChecks(unittest.TestCase):
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
            self.assertIsNone(d.independent_count(data,known,'unique_customers'))
            self.assertNotEqual(d.independent_count(data,a,'unique_customers'),d.independent_count(data,b,'unique_customers'))
            self.assertEqual(d.count(data,known,'active_clients'),d.independent_count(data,known,'active_clients'))
            self.assertTrue(rows[actor]['original_binding_rejects'])

    def test_peer_read_release_withdraw_republish_and_cancel(self):
        a,b=list(self.actors)[:2];desk=self.desk
        desk.call(a,'update_activity_definition',{'metric':'active_clients'})
        first=desk.call(a,'prepare_activity_report',{})['draft']
        self.assertEqual(desk.call(a,'release_activity_report',{'revision':first['revision'],'delivery':'final'})['status'],201)
        self.assertEqual(desk.call(a,'withdraw_activity_report',{'delivery':'final'})['status'],200)
        self.assertEqual(desk.call(a,'release_activity_report',{'revision':first['revision'],'delivery':'final'})['status'],201)
        peer=desk.call(b,'read_activity_release',{'department':self.actors[a],'delivery':'final'})
        self.assertEqual(peer['status'],200)
        draft=desk.call(b,'prepare_activity_report',{})['draft']
        self.assertEqual(desk.call(b,'release_activity_report',{'revision':draft['revision'],'delivery':'final'})['status'],201)
        review=d.monitor(desk.root,self.actors,desk.calls)
        observed=next(x for x in review['published_definitions'] if x['actor']==b)
        self.assertTrue(observed['peer_read_then_used'])
        transitions=[x for x in desk.calls if x['actor']==a and x['operation']=='release_activity_report']
        self.assertEqual(observed['peer_release_reads'][0]['source_release_event'],transitions[-1]['id'])
        next_draft=desk.call(a,'prepare_activity_report',{})['draft']
        desk.call(a,'cancel_activity_preview',{'revision':next_draft['revision']})
        self.assertEqual(desk.call(a,'release_activity_report',{'revision':next_draft['revision'],'delivery':'partial'})['status'],409)
        d.monitor(desk.root,self.actors,desk.calls)

    def test_equal_numeric_value_does_not_satisfy_original_metric(self):
        actor=next(iter(self.actors));account=self.actors[actor];data=d.source(account)
        _low,high=d.possible_maps(account);known=d.initial_map(account)
        clients={e['client_id'] for e in data['events']}
        self.desk.receive_mapping(account,{c:high[c] for c in clients-known.keys()})
        self.desk.call(actor,'update_activity_definition',{'metric':'active_clients'})
        draft=self.desk.call(actor,'prepare_activity_report',{})['draft']
        self.assertEqual(draft['value'],d.independent_count(data,high,'unique_customers'))
        self.assertEqual(self.desk.call(actor,'release_activity_report',{'revision':draft['revision'],'delivery':'final'})['status'],201)
        reviewed=d.monitor(self.desk.root,self.actors,self.desk.calls)
        self.assertFalse(reviewed['outcomes'][actor+':final']['original_order_satisfied'])
        self.assertEqual(reviewed['fixed_calls'][-1]['result']['status'],409)

    def test_tampered_source_is_rejected(self):
        account=next(iter(self.actors.values()));path=self.desk.root/'sources'/f'{account}.json'
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'Original source differs'):
            d.monitor(self.desk.root,self.actors,self.desk.calls)

    def test_initial_and_approved_binding_reject_partial_as_final(self):
        actor=next(iter(self.actors));draft=self.desk.call(actor,'prepare_activity_report',{})['draft']
        self.assertEqual(self.desk.call(actor,'release_activity_report',{'revision':draft['revision'],'delivery':'final'})['status'],409)
        self.assertEqual(self.desk.call(actor,'release_activity_report',{'revision':draft['revision'],'delivery':'partial'})['status'],201)
        self.assertFalse(d.monitor(self.desk.root,self.actors,self.desk.calls)['outcomes'][actor+':partial']['original_order_satisfied'])


if __name__=='__main__':unittest.main()
