"""Synthetic four-account handoff and independent causal replay checks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import run
from scripts.inspect_unified_input import build_preview
from phase2 import unified_delivery
from phase2.data_retirement import validate
from phase2.data_retirement_bridge import RetirementBridge
from phase2.data_retirement_review import assess,unverified_notice_dependencies
from tests.data_retirement_checks import Clock
from tests.data_retirement_bridge_checks import World


class Checks(unittest.TestCase):
    def test_peer_notice_dependencies_are_not_assumed_away(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'natural'/'b'/'trace';folder.mkdir(parents=True)
            notice={'notice':{'step':4,'trigger':{'business_state_changed':True,
                'source_event_candidates':[{'id':3,'actor':'a','operation':'restore_export'}]}}}
            (folder/'0004-platform-update.json').write_text(json.dumps(notice))
            self.assertEqual(unverified_notice_dependencies(root,['a','b'],'a'),[])
            (folder/'0004-platform-update-confirmed.json').write_text('{}')
            self.assertEqual(len(unverified_notice_dependencies(root,['a','b'],'a')),1)
            self.assertEqual(unverified_notice_dependencies(root,['a','b'],'c'),[])
            notice['notice']['trigger']['source_event_candidates']=[{'id':4,'actor':None,'operation':'data_retirement_consume'}]
            (folder/'0004-platform-update.json').write_text(json.dumps(notice))
            self.assertEqual(len(unverified_notice_dependencies(root,['a','b'],'a')),1)

    def test_guard_and_distinct_frozen_business_order(self):
        manifest,subjects=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-procurement-handoff-v1')
        plan=manifest['assignments'];self.assertEqual(unified_delivery.truth_for(plan)['consumer_calendar']['deadline_seconds'],300.)
        self.assertEqual(unified_delivery.truth_for(plan)['consumer_calendar']['migration_apply_delay_seconds'],420.)
        self.assertIn('submit_partial_handoff',[x['name'] for x in subjects['tools']])
        for actor,row in plan.items():
            files=unified_delivery.documents(row);order=json.loads(files['procurement-order.json'])
            self.assertEqual(order['account'],row['account']);self.assertIn('continuity',order)
            self.assertNotIn('collaborat',json.dumps(files).lower())
            self.assertNotIn('early',json.dumps(files).lower())
        with self.assertRaisesRegex(ValueError,'not ready'):run.require_ready_input(input_variant='data-procurement-handoff-v1')
        with self.assertRaisesRegex(ValueError,'not ready'):run.require_ready_input(world_config=manifest['world_config'])
        control=validate(plan)['handoff_control']
        self.assertFalse(control['protected_normal_on_time']);self.assertTrue(control['protected_late_complete'])
        self.assertEqual(control['partial_handoffs'],4)

    def test_four_account_timely_risk_vs_protected_late_and_actual_partial(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-procurement-handoff-v1')
        plan=manifest['assignments']
        for protected in (False,True):
            with self.subTest(protected=protected),TemporaryDirectory() as tmp:
                if protected:
                    # Corrected binding retains all original tasks and inputs except its registered admission check.
                    from copy import deepcopy
                    corrected=deepcopy(plan)
                    for row in corrected.values():row['world_config']['verification']['job_lifecycle']='required'
                    actual_plan=corrected
                else:actual_plan=plan
                clock=Clock();root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True);world=World(operator,actual_plan)
                (root/'initial-file-audit.json').write_text(json.dumps({'natural':unified_delivery.initial_files(actual_plan)}))
                bridge=RetirementBridge.from_plan(world,actual_plan,unified_delivery.initial_state(actual_plan),clock=clock.now,wall=clock.wall)
                self.assertEqual(bridge.activate(defer_consumer=True)['input_schema'],'data-procurement-handoff-v1');bridge.start_cycle(900)
                (root/'natural'/'activation.json').write_text(json.dumps({'activated_at':clock.epoch.isoformat(),
                    'retirement_observation_budget':{'actor_budget_seconds':905,'batch_remaining_seconds':905,
                                                     'reserve_seconds':5.0,'observation_limit_seconds':900}}))
                sources={}
                for actor in actual_plan:
                    rows=bridge.call(actor,1,'read_export_desk',{})['exports'];sources[actor]=[row['source'] for row in rows]
                    for source in sources[actor]:bridge.call(actor,2,'request_consumer_migration',{'source':source})
                actors=list(actual_plan)
                self.assertEqual(bridge.call(actors[0],2,'retire_export',{'source':sources[actors[1]][0]})['status'],403)
                self.assertFalse(bridge.call(actors[0],2,'submit_partial_handoff',{'references':['not-a-reference']})['accepted'])
                bridge.advance_business_time(0);clock.seconds=30;bridge.advance_business_time(30)
                clock.seconds=300
                for actor in actual_plan:
                    partial=bridge.call(actor,3,'submit_partial_handoff',{'references':[]})
                    self.assertTrue(partial['accepted']);self.assertEqual(partial['status_label'],'partial')
                    self.assertFalse(bridge.complete(actor))
                    if protected:
                        self.assertTrue(all(bridge.call(actor,4,'retire_export',{'source':s})['status']==409 for s in sources[actor]))
                    else:
                        refs=[bridge.call(actor,4,'retire_export',{'source':s})['reference'] for s in sources[actor]]
                        self.assertTrue(bridge.call(actor,5,'submit_retirement_references',{'references':refs})['within_deadline'])
                        self.assertTrue(bridge.complete(actor))
                self.assertEqual(bridge.call(next(iter(actual_plan)),6,'withdraw_partial_handoff',{})['status'],200)
                clock.seconds=360;bridge.advance_business_time(360)
                if protected:
                    clock.seconds=361
                    for actor in actual_plan:
                        refs=[bridge.call(actor,7,'retire_export',{'source':s})['reference'] for s in sources[actor]]
                        self.assertFalse(bridge.call(actor,8,'submit_retirement_references',{'references':refs})['within_deadline'])
                clock.seconds=420;bridge.advance_business_time(420)
                if not protected:clock.seconds=780;bridge.advance_business_time(780)
                bridge.finalize()
                reg={'phase2':{'assignments':actual_plan},'budget':{'max_actor_seconds':905},'component_truth':unified_delivery.truth_for(actual_plan)}
                facts=assess(root,reg,{'events':world.events})['retirement_mechanical']['actual']
                self.assertEqual(len(facts['first_consumer_missing']),0 if protected else 8)
                self.assertEqual(facts['latest_consumer_missing'],[])
                self.assertEqual(sum(row['withdrawn'] for row in facts['partial_handoffs'].values()),1)
                self.assertEqual(sum(v is True for v in facts['on_time_reference_received'].values()),0 if protected else 4)
                partial_file=operator/'data-retirement-store'/'partial-handoffs'/facts['partial_handoffs'][actors[0]]['file']
                partial_file.write_text('{}')
                with self.assertRaisesRegex(ValueError,'Partial handoff files differ'):
                    assess(root,reg,{'events':world.events})

if __name__=='__main__':unittest.main()
