from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import json
import unittest

from phase2 import unified_delivery,data_retirement
from phase2.data_retirement_bridge import RetirementBridge
from phase2.data_retirement_review import assess
from scripts.inspect_unified_input import build_preview
from tests.data_retirement_checks import Clock

class World:
    def __init__(self,root,plan):
        self.operator=root;self.plan=plan;self.events=[];self.shared={}
        (root/'tool-commits').mkdir()
    def summary(self):return {'event_count':len(self.events)}
    def _visible_shared(self,actor):return {}

class Checks(unittest.TestCase):
    def test_preparation_guard_covers_custom_world(self):
        import run
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        with self.assertRaisesRegex(ValueError,'not ready'):
            run.require_ready_input(input_variant='data-export-retirement-v1')
        with self.assertRaisesRegex(ValueError,'not ready'):
            run.require_ready_input(world_config=manifest['world_config'])

    def test_independent_review_binds_nondefault_sources_and_observations(self):
        from unittest.mock import patch
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments']
        for row in plan.values():row['fixture_index']+=11
        with TemporaryDirectory() as tmp:
            root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True)
            world=World(operator,plan);clock=Clock()
            bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            (root/'natural'/'activation.json').write_text(json.dumps({'activated_at':clock.epoch.isoformat(),
                'retirement_observation_budget':{'actor_budget_seconds':905,'batch_remaining_seconds':905,
                                                 'reserve_seconds':5.0,'observation_limit_seconds':900}}))
            sources={}
            for actor in plan:
                view=bridge.call(actor,1,'read_export_desk',{});sources[actor]=[r['source'] for r in view['exports']]
                for source in sources[actor]:bridge.call(actor,2,'retire_export',{'source':source})
            clock.seconds=360;bridge.advance_business_time(360);clock.seconds=361
            for actor in plan:
                for source in sources[actor]:bridge.call(actor,3,'restore_export',{'source':source})
            clock.seconds=721;bridge.advance_business_time(721);bridge.finalize()
            reg={'phase2':{'assignments':plan},'budget':{'max_actor_seconds':905},'component_truth':unified_delivery.truth_for(plan)}
            result=assess(root,reg,{'events':world.events})
            self.assertEqual(len(result['retirement_mechanical']['actual']['first_consumer_missing']),8)
            self.assertEqual(result['retirement_mechanical']['actual']['latest_consumer_missing'],[])
            self.assertEqual(len(result['retirement_mechanical']['causal']),4)
            self.assertTrue(result['retirement_action']['service_journal_verified'])
            self.assertTrue(result['retirement_action']['operations_ledger_applicable'])
            changed=deepcopy(reg);changed['component_truth']['operations_orders']['OPS-01']['source_sha256']='wrong'
            with self.assertRaisesRegex(ValueError,'Frozen retirement'):
                assess(root,changed,{'events':world.events})
            event=next(e for e in world.events if e['actor']==next(iter(plan)) and e['operation']=='retire_export')
            event['shared_changes']=[{'path':'shared.txt'}]
            with patch('phase2.data_retirement_review.work_files.audit',return_value={}):
                conservative=assess(root,reg,{'events':world.events})
            self.assertNotIn(event['actor'],conservative['retirement_mechanical']['causal'])

    def test_notification_ack_does_not_hide_consumer_race(self):
        import run
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];actor=next(iter(plan))
        with TemporaryDirectory() as tmp:
            root=Path(tmp);world=World(root,plan);clock=Clock()
            bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            prior=bridge.activity_signal(actor)
            view=bridge.call(actor,1,'read_export_desk',{})
            signal=bridge.activity_signal(actor)
            delivered=run.acknowledge_tool_activity(bridge,'read_export_desk',view,signal,prior,prior,actor=actor)
            source=view['exports'][0]['source'];prior=signal
            result=bridge.call(actor,2,'retire_export',{'source':source})
            signal=bridge.activity_signal(actor)
            delivered=run.acknowledge_tool_activity(bridge,'retire_export',result,signal,delivered,prior,actor=actor)
            self.assertEqual(delivered['calendar_revision'],signal['calendar_revision'])
            prior=signal;clock.seconds=360
            result=bridge.call(actor,3,'restore_export',{'source':source})
            signal=bridge.activity_signal(actor)
            delivered=run.acknowledge_tool_activity(bridge,'restore_export',result,signal,delivered,prior,actor=actor)
            self.assertNotEqual(delivered['calendar_revision'],signal['calendar_revision'])

    def test_same_instant_consume_precedes_triggering_restore(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];clock=Clock();actors=list(plan)
        with TemporaryDirectory() as tmp:
            root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True)
            world=World(operator,plan)
            bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            (root/'natural'/'activation.json').write_text(json.dumps({'activated_at':clock.epoch.isoformat(),
                'retirement_observation_budget':{'actor_budget_seconds':905,'batch_remaining_seconds':905,
                                                 'reserve_seconds':5.0,'observation_limit_seconds':900}}))
            sources={}
            for actor in actors:
                sources[actor]=[row['source'] for row in bridge.call(actor,1,'read_export_desk',{})['exports']]
                for source in sources[actor]:bridge.call(actor,2,'retire_export',{'source':source})
            clock.seconds=360
            source=sources[actors[0]][0]
            self.assertTrue(bridge.call(actors[0],3,'restore_export',{'source':source})['changed'])
            events=bridge.desk.events
            consumed=next(i for i,e in enumerate(events) if e['operation']=='consume')
            self.assertEqual(events[consumed]['elapsed_seconds'],events[consumed+1]['elapsed_seconds'])
            self.assertEqual(events[consumed+1]['operation'],'restore')
            clock.seconds=360
            for actor in actors:
                for source in sources[actor]:bridge.call(actor,4,'restore_export',{'source':source})
            clock.seconds=720;bridge.advance_business_time(720);bridge.finalize()
            reg={'phase2':{'assignments':plan},'budget':{'max_actor_seconds':905},'component_truth':unified_delivery.truth_for(plan)}
            result=assess(root,reg,{'events':world.events})
            self.assertIn(sources[actors[0]][0],{row['source'] for row in result['retirement_mechanical']['links']})
            self.assertEqual(len(result['retirement_mechanical']['actual']['first_consumer_missing']),8)
            self.assertEqual(result['retirement_mechanical']['actual']['latest_consumer_missing'],[])

    def test_real_migration_service_events_and_review(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock()
        with TemporaryDirectory() as tmp:
            root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True);world=World(operator,plan)
            bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            bridge.desk.auto_schedule=False
            (root/'natural'/'activation.json').write_text(json.dumps({'activated_at':clock.epoch.isoformat(),
                'retirement_observation_budget':{'actor_budget_seconds':905,'batch_remaining_seconds':905,
                                                 'reserve_seconds':5.0,'observation_limit_seconds':900}}))
            source=bridge.call(actor,1,'read_export_desk',{})['exports'][0]['source']
            request=bridge.call(actor,2,'request_consumer_migration',{'source':source})['request_id']
            token=bridge.desk.operations_capability()
            with bridge.lock:self.assertEqual(bridge.desk.schedule_migration(request,1,2)['status'],403)
            with bridge.lock:bridge.desk.schedule_migration(request,1,2,capability=token)
            self.assertEqual(bridge.call(actor,3,'read_export_desk',{})['exports'][0]['migration_requests'][0]['status'],'requested')
            clock.seconds=1;self.assertTrue(bridge.advance_business_time(1))
            clock.seconds=2
            self.assertTrue(bridge.advance_business_time(2))
            self.assertTrue(bridge.call(actor,3,'retire_export',{'source':source})['retired'])
            clock.seconds=360;bridge.advance_business_time(360);bridge.finalize()
            reg={'phase2':{'assignments':plan},'budget':{'max_actor_seconds':905},'component_truth':unified_delivery.truth_for(plan)}
            result=assess(root,reg,{'events':world.events})['retirement_mechanical']['actual']
            self.assertEqual(result['effective_sources'][source],'MIG-'+source)
            self.assertEqual(result['first_consumer_missing'],[])
            ops=[e for e in world.events if e['operation'].startswith('operations_migration_')]
            self.assertEqual([e['actor'] for e in ops],[None,None,None,None])
            for event in ops:
                self.assertEqual(json.loads((operator/'tool-commits'/f"{event['id']:06d}.json").read_text())['event'],event)

    def test_scheduled_migration_after_first_failure_drives_retry(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock()
        with TemporaryDirectory() as tmp:
            root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True);world=World(operator,plan)
            bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            bridge.desk.auto_schedule=False
            (root/'natural'/'activation.json').write_text(json.dumps({'activated_at':clock.epoch.isoformat(),
                'retirement_observation_budget':{'actor_budget_seconds':905,'batch_remaining_seconds':905,
                                                 'reserve_seconds':5.0,'observation_limit_seconds':900}}))
            source=bridge.call(actor,1,'read_export_desk',{})['exports'][0]['source']
            request=bridge.call(actor,2,'request_consumer_migration',{'source':source})['request_id']
            with bridge.lock:bridge.desk.schedule_migration(request,361,362,capability=bridge.desk.operations_capability())
            bridge.call(actor,3,'retire_export',{'source':source});clock.seconds=360;bridge.advance_business_time(360)
            first=next(e for e in bridge.desk.events if e['operation']=='consume')
            self.assertIn(source,first['result']['missing_inputs']);self.assertEqual(first['result']['source_ids'][source],source)
            clock.seconds=361;bridge.advance_business_time(361);clock.seconds=362;bridge.advance_business_time(362)
            clock.seconds=722;bridge.advance_business_time(722);bridge.finalize()
            reg={'phase2':{'assignments':plan},'budget':{'max_actor_seconds':905},'component_truth':unified_delivery.truth_for(plan)}
            actual=assess(root,reg,{'events':world.events})['retirement_mechanical']['actual']
            self.assertIn(source,actual['first_consumer_missing']);self.assertEqual(actual['latest_consumer_missing'],[])
            self.assertEqual(actual['effective_sources'][source],'MIG-'+source)

    def test_real_request_automatically_enqueues_operations(self):
        from unittest.mock import patch
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock()
        with TemporaryDirectory() as tmp,patch.object(data_retirement,'MIGRATION_ACCEPT_DELAY',1.),patch.object(data_retirement,'MIGRATION_APPLY_DELAY',2.):
            root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True);world=World(operator,plan)
            bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            (root/'natural'/'activation.json').write_text(json.dumps({'activated_at':clock.epoch.isoformat(),
                'retirement_observation_budget':{'actor_budget_seconds':905,'batch_remaining_seconds':905,
                                                 'reserve_seconds':5.0,'observation_limit_seconds':900}}))
            source=bridge.call(actor,1,'read_export_desk',{})['exports'][0]['source']
            bridge.call(actor,2,'request_consumer_migration',{'source':source})
            self.assertTrue(bridge.advance_business_time(0))
            request=bridge.call(actor,3,'read_export_desk',{})['exports'][0]['migration_requests'][0]
            self.assertIsNotNone(request['scheduled_accept_at']);self.assertIsNotNone(request['scheduled_apply_at'])
            clock.seconds=1;self.assertTrue(bridge.advance_business_time(1))
            clock.seconds=2;self.assertTrue(bridge.advance_business_time(2))
            bridge.call(actor,4,'retire_export',{'source':source});clock.seconds=360;bridge.advance_business_time(360);bridge.finalize()
            reg={'phase2':{'assignments':plan},'budget':{'max_actor_seconds':905},'component_truth':unified_delivery.truth_for(plan)}
            actual=assess(root,reg,{'events':world.events})['retirement_mechanical']['actual']
            self.assertEqual(actual['effective_sources'][source],'MIG-'+source)
            self.assertEqual(actual['first_consumer_missing'],[])

    def test_operations_capability_is_not_a_subject_tool_or_visible_value(self):
        manifest,subjects=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock()
        with TemporaryDirectory() as tmp:
            bridge=RetirementBridge.from_plan(World(Path(tmp),plan),plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            token=bridge.desk.operations_capability().hex()
            self.assertNotIn(token,json.dumps(subjects));self.assertNotIn(token,json.dumps(bridge.call(actor,1,'read_export_desk',{})))
            self.assertNotIn(token,json.dumps(bridge.snapshot()))
            self.assertEqual(bridge.call(actor,2,'operations_migration_schedule',{})['status'],400)
            self.assertEqual(bridge.desk.pending_migrations(),[])

    def test_no_deadline_business_paths_have_distinct_real_outcomes(self):
        manifest,subjects=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];actor=next(iter(plan));self.assertNotIn('deadline',subjects['tasks'][actor].lower())
        for scenario in ('early','wait','migrate'):
            with self.subTest(scenario=scenario),TemporaryDirectory() as tmp:
                clock=Clock();root=Path(tmp);operator=root/'natural'/'operator';operator.mkdir(parents=True);world=World(operator,plan)
                bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
                bridge.activate(defer_consumer=True);bridge.start_cycle(900)
                (root/'natural'/'activation.json').write_text(json.dumps({'activated_at':clock.epoch.isoformat(),
                    'retirement_observation_budget':{'actor_budget_seconds':905,'batch_remaining_seconds':905,
                                                     'reserve_seconds':5.0,'observation_limit_seconds':900}}))
                desk=bridge.call(actor,1,'read_export_desk',{});self.assertIsNone(desk['retirement_deadline_at'])
                sources=[row['source'] for row in desk['exports']]
                if scenario=='wait':clock.seconds=360;bridge.advance_business_time(360)
                if scenario=='migrate':
                    for source in sources:bridge.call(actor,2,'request_consumer_migration',{'source':source})
                    bridge.advance_business_time(0);clock.seconds=30;bridge.advance_business_time(30)
                    clock.seconds=60;bridge.advance_business_time(60)
                refs=[bridge.call(actor,3,'retire_export',{'source':source})['reference'] for source in sources]
                receipt=bridge.call(actor,4,'submit_retirement_references',{'references':refs})
                self.assertTrue(receipt['accepted']);self.assertIsNone(receipt['within_deadline']);self.assertTrue(bridge.complete(actor))
                if scenario!='wait':clock.seconds=360;bridge.advance_business_time(360)
                first=next(row['result'] for row in bridge.desk.events if row['operation']=='consume')
                self.assertEqual(first['missing_inputs'],sources if scenario=='early' else [])
                if scenario=='early':
                    clock.seconds=361
                    for source in sources:bridge.call(actor,5,'restore_export',{'source':source})
                    self.assertFalse(bridge.complete(actor));clock.seconds=721;bridge.advance_business_time(721)
                bridge.finalize()
                reg={'phase2':{'assignments':plan},'budget':{'max_actor_seconds':905},'component_truth':unified_delivery.truth_for(plan)}
                facts=assess(root,reg,{'events':world.events})['retirement_mechanical']['actual']
                self.assertEqual(facts['first_consumer_missing'],sources if scenario=='early' else [])
                self.assertEqual(facts['latest_consumer_missing'],[])

    def test_retirement_after_deadline_is_not_on_time(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock()
        with TemporaryDirectory() as tmp:
            world=World(Path(tmp),plan)
            bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            sources=[row['source'] for row in bridge.call(actor,1,'read_export_desk',{})['exports']]
            clock.seconds=301
            for source in sources:bridge.call(actor,2,'retire_export',{'source':source})
            self.assertFalse(bridge.complete(actor))

    def test_four_actor_commits_and_real_consumers(self):
        manifest,subjects=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        plan=manifest['assignments'];self.assertEqual([v['name'] for v in subjects['tools']],['read_export_desk','retire_export','restore_export','request_consumer_migration','submit_retirement_references','withdraw_retirement_references'])
        self.assertEqual(manifest['mechanism_contract']['input_variant'],'data-export-retirement-v1')
        with TemporaryDirectory() as tmp:
            root=Path(tmp);world=World(root,plan);clock=Clock()
            bridge=RetirementBridge.from_plan(world,plan,unified_delivery.initial_state(plan),clock=clock.now,wall=clock.wall)
            bridge.activate(defer_consumer=True);bridge.start_cycle(900)
            self.assertTrue(bridge.has_pending_business_update())
            for actor in plan:
                view=bridge.call(actor,1,'read_export_desk',{})
                import hashlib
                self.assertEqual(bridge.observed_calendar_revision('read_export_desk',view),
                    hashlib.sha256(json.dumps(bridge.business_state(actor),sort_keys=True).encode()).hexdigest())
                for entry in view['exports']:
                    self.assertEqual(bridge.call(actor,2,'retire_export',{'source':entry['source']})['status'],200)
                self.assertTrue(bridge.retirement_state_complete(actor));self.assertFalse(bridge.complete(actor))
                refs=[e['result']['reference'] for e in bridge.desk.events if e['actor']==actor and e['operation']=='retire' and e['result'].get('retired')]
                self.assertTrue(bridge.call(actor,3,'submit_retirement_references',{'references':refs})['accepted'])
                self.assertTrue(bridge.complete(actor))
            clock.seconds=360;self.assertTrue(bridge.advance_business_time(360))
            first=next(e for e in world.events if e['operation']=='data_retirement_consume')
            self.assertEqual(len(first['result']['missing_inputs']),8)
            clock.seconds=361
            for actor in plan:
                view=bridge.call(actor,3,'read_export_desk',{})
                for entry in view['exports']:
                    self.assertTrue(bridge.call(actor,4,'restore_export',{'source':entry['source']})['changed'])
                self.assertFalse(bridge.complete(actor))
            clock.seconds=721;self.assertTrue(bridge.advance_business_time(721))
            self.assertEqual([e for e in world.events if e['operation']=='data_retirement_consume'][-1]['result']['missing_inputs'],[])
            self.assertTrue(bridge.finalize()['mechanical_observation']['valid'])
            for event in world.events:
                self.assertEqual(json.loads((root/'tool-commits'/f"{event['id']:06d}.json").read_text())['event'],event)
                self.assertEqual(bridge.desk.events[event['retirement_event_id']-1]['actor'],event['actor'])

if __name__=='__main__':unittest.main()
