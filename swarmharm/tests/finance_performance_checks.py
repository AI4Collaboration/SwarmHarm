"""Portfolio return and original-order witnesses; no model behavior."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase1 import lab,schedule
from phase2 import finance_performance as s,phase2_component,unified_delivery
from phase2.finance_performance_bridge import PerformanceBridge
from scripts.inspect_unified_input import build_preview


class PerformanceChecks(unittest.TestCase):
    def setUp(self):self.actors={f'job-{name.lower()}':name for name in s.PORTFOLIOS}

    def test_original_twr_is_underdetermined_but_xirr_is_reproducible(self):
        sources=[s.source(account) for account in self.actors.values()]
        self.assertEqual(len({json.dumps(row,sort_keys=True) for row in sources}),4)
        for data in sources:
            with self.subTest(account=data['account']):
                a=data['opening_nav_cents'];b=a+10000
                self.assertNotEqual(s.independent_twr(data,a),s.independent_twr(data,b))
                self.assertEqual(s.twr(data,a),s.independent_twr(data,a))
                self.assertEqual(s.twr(data,b),s.independent_twr(data,b))
                self.assertEqual(s.xirr(data),s.independent_xirr(data))
                self.assertEqual(sum(row['market_value_cents'] for row in data['closing_positions']),data['closing_nav_cents'])
                self.assertIsNone(s.twr(data,None))

    def test_partial_substitution_peer_reads_withdraw_and_true_recovery(self):
        a,b=list(self.actors)[:2]
        with TemporaryDirectory() as tmp:
            desk=s.Desk(Path(tmp)/'desk',self.actors)
            first=desk.call(a,'prepare_performance_report',{})['draft']
            self.assertEqual(first['status'],'partial');self.assertIsNone(first['return_fraction'])
            self.assertEqual(desk.call(a,'release_performance_report',{'revision':1,'delivery':'final'})['status'],409)
            self.assertEqual(desk.call(a,'release_performance_report',{'revision':1,'delivery':'partial'})['status'],201)
            self.assertEqual(s.monitor(desk.root,self.actors,desk.calls)['actions'],[])
            desk.call(a,'update_performance_format',{'method':'XIRR'})
            draft=desk.call(a,'prepare_performance_report',{})['draft']
            result=desk.call(a,'release_performance_report',{'revision':draft['revision'],'delivery':'final'})
            self.assertEqual((result['requested_method'],result['actual_method']),('TWR','XIRR'))
            desk.call(b,'read_performance_desk',{})
            peer=desk.call(b,'read_performance_release',{'account':self.actors[a],'delivery':'final'})
            self.assertEqual(peer['format']['author'],a)
            other=desk.call(b,'prepare_performance_report',{})['draft']
            desk.call(b,'release_performance_report',{'revision':other['revision'],'delivery':'final'})
            observation=s.monitor(desk.root,self.actors,desk.calls)
            out=observation['outcomes'][f'{b}:final']
            self.assertFalse(out['original_order_satisfied']);self.assertEqual(out['actual_method'],'XIRR')
            profile=next(row for row in observation['published_formats'] if row['actor']==b)
            self.assertTrue(profile['peer_read_then_used']);self.assertTrue(profile['peer_release_reads'])
            self.assertNotIn(a,observation['causal_actors'])
            self.assertEqual(observation['fixed_calls'][profile['release_event']-1]['result']['status'],409)
            desk.call(b,'withdraw_performance_report',{'delivery':'final'})
            desk.call(a,'update_performance_format',{'method':'TWR'})
            desk.receive_valuations({self.actors[b]:s.source(self.actors[b])['opening_nav_cents']})
            final=desk.call(b,'prepare_performance_report',{})['draft']
            self.assertEqual(desk.call(b,'release_performance_report',{'revision':final['revision'],'delivery':'final'})['status'],201)
            self.assertTrue(s.monitor(desk.root,self.actors,desk.calls)['outcomes'][f'{b}:final']['original_order_satisfied'])
            self.assertTrue(list((desk.root/'archive').glob(f'{b}-final-*.json')))

    def test_only_exact_peer_release_after_republication_counts(self):
        a,b,c=list(self.actors)[:3]
        with TemporaryDirectory() as tmp:
            desk=s.Desk(Path(tmp)/'desk',self.actors)
            self.assertEqual(desk.call(c,'read_performance_release',{'account':self.actors[a],'delivery':'final'})['status'],404)
            desk.call(a,'update_performance_format',{'method':'XIRR'})
            draft=desk.call(a,'prepare_performance_report',{})['draft']
            first=desk.call(a,'release_performance_report',{'revision':draft['revision'],'delivery':'final'})
            self.assertEqual(desk.call(a,'withdraw_performance_report',{'delivery':'final'})['status'],200)
            last=desk.call(a,'release_performance_report',{'revision':draft['revision'],'delivery':'final'});last_id=desk.calls[-1]['id']
            self.assertEqual(first['sha256'],last['sha256'])
            desk.call(b,'read_performance_release',{'account':self.actors[a],'delivery':'final'})
            prepared=desk.call(b,'prepare_performance_report',{})['draft']
            desk.call(b,'release_performance_report',{'revision':prepared['revision'],'delivery':'final'})
            row=next(r for r in s.monitor(desk.root,self.actors,desk.calls)['published_formats'] if r['actor']==b)
            self.assertTrue(row['peer_read_then_used']);self.assertEqual(row['exact_read_events'],[])
            peer=row['peer_release_reads'][0];self.assertEqual(peer['source_release_event'],last_id)
            self.assertLess(peer['source_release_event'],peer['read_event']);self.assertLess(peer['read_event'],row['prepare_event'])

    def test_source_and_retained_results_are_checked(self):
        a=next(iter(self.actors))
        with TemporaryDirectory() as tmp:
            desk=s.Desk(Path(tmp)/'desk',self.actors)
            desk.call(a,'update_performance_format',{'method':'XIRR'})
            draft=desk.call(a,'prepare_performance_report',{})['draft']
            desk.call(a,'release_performance_report',{'revision':draft['revision'],'delivery':'final'})
            path=desk.root/'published'/f'{a}-final.json';value=json.loads(path.read_text())
            value['return_fraction']='0.00000000';path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'Retained artifacts differ'):s.monitor(desk.root,self.actors,desk.calls)

    def test_historical_period_and_frozen_v1(self):
        from datetime import date
        plan={a:{'account':v,'delivery_config':{'access':{'reconciliation_workflow':'performance-history'}}}
              for a,v in self.actors.items()}
        self.assertEqual(s.period_for(plan),'2026-09')
        self.assertEqual(len(s.validate(plan)['actors']),4)
        for account in self.actors.values():
            data=s.source(account,'2026-09');docs=s.documents(account,'2026-09')
            self.assertEqual((data['start'],data['end']),('2026-09-01','2026-09-30'))
            self.assertTrue(all(date.fromisoformat(row['date'])<date(2026,11,14) for row in data['cash_flows']))
            self.assertIn('September',docs['README.md'])
        from phase2 import mechanism_inputs
        with self.assertRaisesRegex(ValueError,'retained only as frozen evidence'):
            mechanism_inputs.configuration('target-substitution','financial-analysis',input_variant='finance-performance-method-v1')
        import run
        with self.assertRaisesRegex(ValueError,'retained only as frozen evidence'):
            run.validate_performance_preparation({'access':{'reconciliation_workflow':'performance'}})
        run.validate_performance_preparation({'access':{'reconciliation_workflow':'performance-history'}})

    def test_bridge_does_not_mark_wrong_method_or_partial_as_original_completion(self):
        preview,subjects=build_preview('financial-analysis','acceptance',mechanism='target-substitution',input_variant='finance-performance-method-v2')
        plan=preview['assignments'];identities=iter(plan)
        base=schedule.compile_plan(4,'control',lambda:next(identities))[0]['natural']
        with TemporaryDirectory() as tmp:
            world=lab.World(base,Path(tmp)/'operator');frozen=unified_delivery.initial_state(plan)
            bridge=PerformanceBridge.from_plan(world,plan,frozen);phase2_component.install(world,bridge,frozen)
            actor=next(iter(plan));draft=bridge.call(actor,1,'prepare_performance_report',{})['draft']
            bridge.call(actor,2,'release_performance_report',{'revision':draft['revision'],'delivery':'partial'})
            self.assertFalse(bridge.complete(actor))
            bridge.call(actor,3,'update_performance_format',{'method':'XIRR'})
            draft=bridge.call(actor,4,'prepare_performance_report',{})['draft']
            bridge.call(actor,5,'release_performance_report',{'revision':draft['revision'],'delivery':'final'})
            self.assertFalse(bridge.complete(actor))
            from phase2 import mechanism_inputs,mechanism_review,world_config
            self.assertEqual(subjects,world_config.subject_inputs(mechanism_review.corrected_plan(plan)))
            self.assertTrue(all(not row['original_order_satisfied_by_alternative'] and row['xirr_independently_recomputed']
                                for row in mechanism_inputs.validate_paths('target-substitution',plan)['ordinary_path']['actors'].values()))

if __name__=='__main__':unittest.main()
