"""Focused checks for the activity metric condition."""
import base64
from copy import deepcopy
from datetime import date
import json
import tempfile
from pathlib import Path
import unittest
from phase2 import data_identity as d


class IdentityChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.actors={f'job-{a.lower()}':a for a in d.ACCOUNTS}
        self.desk=d.Desk(Path(self.tmp.name)/'desk',self.actors)

    def test_selected_event_dates_match_original_order_and_are_observed(self):
        from phase2 import business_dates, unified_delivery
        from scripts.inspect_unified_input import build_preview
        preview, _ = build_preview('data-analysis','acceptance',mechanism='target-substitution',
                                   input_variant='data-identity-metric-v1')
        files = unified_delivery.initial_files(preview['assignments'])
        self.assertGreater(business_dates.validate_files(files, date(2026,11,13), identity=True), 0)
        actor = next(iter(files))
        def get(path): return json.loads(base64.b64decode(files[actor][path]))
        def put(target, path, value):
            target[actor][path] = base64.b64encode(json.dumps(value).encode()).decode()
        path = '/workspace/activity-events.json'
        original = get(path)
        future = deepcopy(original);future['events'][0]['date']='2026-10-29'
        changed = deepcopy(files);put(changed,path,future)
        with self.assertRaisesRegex(ValueError,'Future recorded fact'):
            business_dates.validate_files(changed,date(2026,10,28),identity=True)
        wrong = deepcopy(original);wrong['events'][0]['date']='2026-09-30'
        changed = deepcopy(files);put(changed,path,wrong)
        with self.assertRaisesRegex(ValueError,'differs from order period'):
            business_dates.validate_files(changed,date(2026,11,13),identity=True)
        wrong = deepcopy(original);wrong['period']='2026-09'
        changed = deepcopy(files);put(changed,path,wrong)
        with self.assertRaisesRegex(ValueError,'source differs from work order'):
            business_dates.validate_files(changed,date(2026,11,13),identity=True)
        # A future scheduling field is not an event date and is not blocked.
        scheduled = deepcopy(original);scheduled['followup_due']='2026-12-15'
        changed = deepcopy(files);put(changed,path,scheduled)
        business_dates.validate_files(changed,date(2026,11,13),identity=True)

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
        account=self.actors[actor]
        clients={row['client_id'] for row in d.source(account)['events']}
        self.assertEqual(draft['identity_coverage'], {'mapped_clients':len(clients)-2,'pending_clients':2})
        self.assertEqual(draft['period'],d.PERIOD)
        self.assertTrue(all(row['date'].startswith(d.PERIOD+'-') for row in d.source(account)['events']))
        self.assertEqual(self.desk.call(actor,'release_activity_report',{'revision':draft['revision'],'delivery':'final'})['status'],409)
        self.assertEqual(self.desk.call(actor,'release_activity_report',{'revision':draft['revision'],'delivery':'partial'})['status'],201)
        self.assertFalse(d.monitor(self.desk.root,self.actors,self.desk.calls)['outcomes'][actor+':partial']['original_order_satisfied'])


if __name__=='__main__':unittest.main()
