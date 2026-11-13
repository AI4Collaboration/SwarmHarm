"""Scripted action tests; these are not model behavior."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2.consolidation_adapter import Adapter, bind_native, monitor
from phase2.consolidation_desk import ENTITIES, METRICS


class AdapterChecks(unittest.TestCase):
    def test_registered_inputs_match_control_and_source_provenance(self):
        from scripts.inspect_unified_input import build_preview
        from phase2 import mechanism_inputs, mechanism_review, world_config
        preview, subjects=build_preview('financial-analysis','acceptance',mechanism='target-substitution',
            input_variant='finance-group-consolidation-v1')
        plan=preview['assignments']
        self.assertEqual(subjects,world_config.subject_inputs(mechanism_review.corrected_plan(plan)))
        self.assertFalse(preview['mechanism_contract']['business_material_provenance']['agent_authored'])
        self.assertEqual(mechanism_inputs.validate_paths('target-substitution',plan)['path_validation'],'passed')
        self.assertEqual({t['name'] for t in subjects['tools']},{t['name'] for t in __import__(
            'phase2.consolidation_adapter',fromlist=['definitions']).definitions()})

    def test_complete_sequence_original_binding_and_actor_omission(self):
        actors = {f'agent-{i}': metric for i, metric in enumerate(METRICS, 1)}
        with TemporaryDirectory() as root:
            a = Adapter(root, actors)
            for actor in actors:
                a.call(actor, 'read_group_desk', {})
                a.call(actor, 'prepare_group_report', {})
                self.assertEqual(a.call(actor, 'release_group_report', {'revision':1})['status'],409)
            a.call('agent-1', 'select_group_view', {'entities':list(ENTITIES[:-1])})
            for actor in actors:
                a.call(actor, 'read_group_desk', {})
                a.call(actor, 'prepare_group_report', {})
                self.assertEqual(a.call(actor, 'release_group_report', {'revision':2})['status'],201)
            a.call('agent-2', 'withdraw_group_report', {})
            a.call('agent-3', 'select_group_view', {'entities':list(ENTITIES)})
            a.call('agent-4', 'cancel_group_draft', {'revision':2})
            result = monitor(root, actors, a.calls)
            self.assertEqual(set(result['actual']), {'agent-1','agent-3','agent-4'})
            self.assertEqual(result['corrected'], {})
            self.assertTrue(all(row['omitted_entities'] == ['west'] for row in result['actual'].values()))
            self.assertIn('agent-1', result['candidate_actors_with_changed_retained_statuses'])
            self.assertNotIn('agent-1', result['causal_actors'])
            self.assertTrue(result['actual']['agent-3']['prior_template_read_events'])
            self.assertFalse(result['corrected_results_match'])  # release/withdraw legitimately differ
            path = Path(root)/'operator/native-call-events.jsonl'
            calls = [json.loads(x) for x in path.read_text().splitlines()]
            calls[0]['result']['pending'] = []
            path.write_text(''.join(json.dumps(x)+'\n' for x in calls))
            with self.assertRaisesRegex(ValueError,'journal differs'):
                monitor(root, actors, a.calls)

    def test_invalid_requests_do_not_mutate_business_state(self):
        actors = {f'agent-{i}': metric for i, metric in enumerate(METRICS, 1)}
        with TemporaryDirectory() as root:
            a = Adapter(root, actors)
            self.assertEqual(a.call('agent-1','cancel_group_draft',{'revision':1})['status'],404)
            self.assertEqual(a.call('agent-1','select_group_view',{'entities':['unknown']})['status'],400)
            self.assertEqual(monitor(root,actors,a.calls)['actual'],{})

    def test_scripted_native_and_atif_exact_binding(self):
        actors = {f'agent-{i}': metric for i, metric in enumerate(METRICS, 1)}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'registration.json').write_text(json.dumps({'harness':{'kind':'codex'}}))
            a = Adapter(root/'service', actors)
            world = {'events':[]}
            for actor in actors:
                a.call(actor,'read_group_desk',{})
                row = a.calls[-1]; event_id = row['id']
                event = {'id':event_id,'adapter_event_id':event_id,'actor':actor,
                         'operation':row['operation'],'arguments':row['arguments'],'result':row['result']}
                world['events'].append(event)
                folder=root/'natural'/actor; (folder/'trace').mkdir(parents=True); (folder/'agent').mkdir()
                record={'event_id':event_id,'call_id':'one','name':row['operation'],
                        'arguments':row['arguments'],'result':row['result']}
                (folder/'trace/0001-tool-0001.json').write_text(json.dumps(record))
                (folder/'trace/0002.request.json').write_text(json.dumps({'input':[{'type':'function_call_output',
                    'call_id':'one','output':json.dumps(row['result'],ensure_ascii=False)}]}))
                (folder/'agent/trajectory.json').write_text(json.dumps({'steps':[{'step_id':1,
                    'tool_calls':[{'tool_call_id':'one'}],
                    'extra':{'tool_result_delivery':{'one':{'sdk_delivery_verified':True}}}}]}))
            self.assertEqual(len(bind_native(root,world,actors,a.calls)),4)
            wrong = root/'natural/agent-2/trace/0001-tool-0001.json'
            altered=json.loads(wrong.read_text());altered['result']['pending']=[]
            wrong.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError,'differs from native'):
                bind_native(root,world,actors,a.calls)

    def test_world_bridge_commits_and_replays_real_service_calls(self):
        from phase2.consolidation_bridge import ConsolidationBridge
        from phase2 import unified_delivery
        class World:
            def __init__(self, root, plan):
                self.operator=root; self.plan=plan; self.events=[]; self.shared={}
                (Path(root)/'tool-commits').mkdir()
            def summary(self): return {}
            def _visible_shared(self,actor): return {}
        accounts=('Northline','Aster','Meridian','Harbor')
        plan={f'agent-{i}':{'account':account,'start_group':0} for i,account in enumerate(accounts,1)}
        with TemporaryDirectory() as tmp:
            operator=Path(tmp)/'natural/operator';operator.mkdir(parents=True)
            world=World(operator,plan)
            with patch.object(unified_delivery,'initial_state',return_value={'frozen':True}), \
                 patch.object(unified_delivery,'config_for',return_value={}), \
                 patch.object(unified_delivery,'bindings_for',return_value={'acceptance_binding':'candidate'}), \
                 patch.object(unified_delivery,'documents',side_effect=lambda row:__import__(
                     'phase2.consolidation_desk',fromlist=['files_for']).files_for(row['account'])):
                bridge=ConsolidationBridge.from_plan(world,plan,{'frozen':True})
            bridge.activate()
            for actor in plan:
                bridge.call(actor,1,'read_group_desk',{})
                bridge.call(actor,1,'prepare_group_report',{})
            bridge.call('agent-1',1,'select_group_view',{'entities':list(ENTITIES[:-1])})
            for actor in plan:
                bridge.call(actor,1,'read_group_desk',{})
                bridge.call(actor,1,'prepare_group_report',{})
                self.assertEqual(bridge.call(actor,1,'release_group_report',{'revision':2})['status'],201)
            bridge.call('agent-2',1,'withdraw_group_report',{})
            result=bridge.finalize()['mechanical_observation']
            self.assertEqual(len(result['actual']),3)
            self.assertEqual(len(world.events),len(bridge.adapter.calls))
            self.assertEqual(len(list((operator/'tool-commits').glob('*.json'))),len(world.events))
            for event,call in zip(world.events,bridge.adapter.calls):
                self.assertEqual(event['adapter_event_id'],call['id'])
                self.assertEqual(event['result'],call['result'])
            root=Path(tmp)
            (root/'registration.json').write_text(json.dumps({'harness':{'kind':'codex'}}))
            for actor in plan:
                folder=root/'natural'/actor; (folder/'trace').mkdir(parents=True); (folder/'agent').mkdir()
                events=[e for e in world.events if e['actor']==actor];steps=[]
                for index,event in enumerate(events,1):
                    identity=f"call-{event['id']}"
                    record={'event_id':event['id'],'call_id':identity,'name':event['operation'],
                            'arguments':event['arguments'],'result':event['result']}
                    (folder/'trace'/f'{index:04d}-tool-0001.json').write_text(json.dumps(record))
                    (folder/'trace'/f'{index+1:04d}.request.json').write_text(json.dumps({'input':[
                        {'type':'function_call_output','call_id':identity,
                         'output':json.dumps(event['result'],ensure_ascii=False)}]}))
                    steps.append({'step_id':index,'tool_calls':[{'tool_call_id':identity}],
                        'extra':{'tool_result_delivery':{identity:{'sdk_delivery_verified':True}}}})
                (folder/'agent/trajectory.json').write_text(json.dumps({'steps':steps}))
            self.assertEqual(len(bind_native(root,{'events':world.events},plan,bridge.adapter.calls)),len(world.events))
            from phase2.consolidation_review import mechanical_review
            registration={'phase2':{'assignments':plan},'mechanism_contract':{
                'input_variant':'finance-group-consolidation-v1','criterion':'fixture',
                'semantic_criterion':'fixture','world_sha256':'w','subject_sha256':'s'}}
            reviewed=mechanical_review(root,registration,{'events':world.events},
                {'consolidation_mechanical':result},True)
            candidates=reviewed['template_author_candidates']
            self.assertTrue(candidates)
            self.assertTrue(all(row['actor']=='agent-1' and not row['retained_statuses_match'] for row in candidates))
            self.assertTrue(any(row['release_actor']!='agent-1' and row['peer_plan_read_events'] for row in candidates))
            self.assertNotIn('agent-1',reviewed['causal_actors'])


if __name__ == '__main__':
    unittest.main()
