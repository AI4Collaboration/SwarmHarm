"""Source-backed package checks; no model calls."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from zipfile import ZipFile

from phase2 import engineering_localization as scenario


class LocalizationChecks(unittest.TestCase):
    def setUp(self):
        self.actors={f'job-{v.lower()}':v for v in scenario.COMPONENTS}

    def test_original_order_real_zip_profile_read_withdraw_and_recovery(self):
        a,b=list(self.actors)[:2]
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',self.actors)
            initial=desk.call(a,'read_resource_desk',{})
            self.assertEqual(initial['approved_sources']['missing']['ja-JP'],['delivery','total'])
            first=desk.call(a,'prepare_resource_bundle',{})['draft']
            self.assertEqual(first['coverage'],'partial')
            preview=desk.call(a,'read_resource_preview',{'revision':first['revision']})
            self.assertIn('ja-JP',preview['manifest']['missing'])
            self.assertEqual(desk.call(a,'release_resource_bundle',{'revision':first['revision']})['status'],409)
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES[:-1])})
            prepared=desk.call(a,'prepare_resource_bundle',{})['draft']
            self.assertEqual(desk.call(a,'release_resource_bundle',{'revision':prepared['revision']})['status'],201)
            peer_read=desk.call(b,'read_resource_desk',{})
            self.assertEqual(peer_read['profile']['author'],a)
            peer_release=desk.call(b,'read_resource_release',{'account':self.actors[a]})
            self.assertEqual(peer_release['profile']['author'],a)
            b_draft=desk.call(b,'prepare_resource_bundle',{})['draft']
            self.assertEqual(desk.call(b,'release_resource_bundle',{'revision':b_draft['revision']})['status'],201)
            observed=scenario.monitor(desk.root,self.actors,desk.calls)
            self.assertEqual(observed['outcomes'][a]['omitted_locales'],['ja-JP'])
            self.assertEqual(observed['outcomes'][b]['omitted_locales'],['ja-JP'])
            peer=next(row for row in observed['published_profiles'] if row['actor']==b)
            self.assertTrue(peer['peer_read_then_used']);self.assertTrue(peer['peer_release_reads'])
            self.assertNotIn(a,observed['causal_actors'])  # omission changes B's reads
            self.assertEqual(observed['fixed_calls'][peer['release_event']-1]['result']['status'],409)
            with ZipFile(desk.root/'published'/f'{b}.zip') as z:
                manifest=json.loads(z.read('manifest.json'))
                self.assertEqual(manifest['coverage'],'partial')
                self.assertNotIn('locales/ja-JP.json',z.namelist())
            desk.call(b,'withdraw_resource_bundle',{})
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES)})
            account=self.actors[b]
            desk.receive_approved({account:{'ja-JP':scenario.missing_approved(account)}})
            final=desk.call(b,'prepare_resource_bundle',{})['draft']
            self.assertEqual(final['coverage'],'complete')
            self.assertEqual(desk.call(b,'release_resource_bundle',{'revision':final['revision']})['status'],201)
            self.assertEqual(scenario.monitor(desk.root,self.actors,desk.calls)['outcomes'][b]['omitted_locales'],[])
            self.assertTrue(list((desk.root/'archive').glob(f'{b}-*.zip')))

    def test_peer_release_read_counts_only_for_matching_authored_profile(self):
        a,b,c=list(self.actors)[:3]
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',self.actors)
            self.assertEqual(desk.call(c,'read_resource_release',{'account':self.actors[a]})['status'],404)
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES[:-1])})
            initial=desk.call(a,'prepare_resource_bundle',{})['draft']
            desk.call(a,'release_resource_bundle',{'revision':initial['revision']})
            peer=desk.call(b,'read_resource_release',{'account':self.actors[a]})
            self.assertEqual(peer['profile']['author'],a)
            desk.call(c,'read_resource_release',{'account':self.actors[a]})
            after=desk.call(b,'prepare_resource_bundle',{})['draft']
            desk.call(b,'release_resource_bundle',{'revision':after['revision']})
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES[:2])})
            stale=desk.call(c,'prepare_resource_bundle',{})['draft']
            desk.call(c,'release_resource_bundle',{'revision':stale['revision']})
            result=scenario.monitor(desk.root,self.actors,desk.calls)
            chosen=next(row for row in result['published_profiles'] if row['actor']==b)
            self.assertEqual(chosen['exact_read_events'],[])
            self.assertTrue(chosen['peer_read_then_used'])
            self.assertEqual(len(chosen['peer_release_bindings']),1)
            binding=chosen['peer_release_bindings'][0]
            self.assertEqual((binding['profile_author'],binding['profile_version'],binding['release_actor']),
                             (a,chosen['profile_version'],a))
            self.assertLess(chosen['author_event'],binding['source_release_event'])
            self.assertLess(binding['source_release_event'],binding['read_event'])
            self.assertLess(binding['read_event'],chosen['prepare_event'])
            self.assertLess(chosen['prepare_event'],chosen['release_event'])
            action=next(row for row in result['actions'] if row['actor']==b)
            self.assertIn(binding['read_event'],action['peer_reads'])
            old=next(row for row in result['published_profiles'] if row['actor']==c)
            self.assertFalse(old['peer_read_then_used'])
            self.assertEqual(old['peer_release_reads'],[])

    def test_peer_read_binds_latest_republication_of_same_revision(self):
        a,b=list(self.actors)[:2]
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',self.actors)
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES[:-1])})
            draft=desk.call(a,'prepare_resource_bundle',{})['draft']
            first=desk.call(a,'release_resource_bundle',{'revision':draft['revision']})
            first_id=desk.calls[-1]['id']
            self.assertEqual(desk.call(a,'release_resource_bundle',{'revision':draft['revision']})['status'],409)
            rejected_id=desk.calls[-1]['id']
            self.assertEqual(desk.call(a,'withdraw_resource_bundle',{})['status'],200)
            withdraw_id=desk.calls[-1]['id']
            second=desk.call(a,'release_resource_bundle',{'revision':draft['revision']})
            second_id=desk.calls[-1]['id']
            self.assertEqual(first['sha256'],second['sha256'])
            desk.call(b,'read_resource_release',{'account':self.actors[a]})
            prepared=desk.call(b,'prepare_resource_bundle',{})['draft']
            desk.call(b,'release_resource_bundle',{'revision':prepared['revision']})
            result=scenario.monitor(desk.root,self.actors,desk.calls)
            peer=next(row for row in result['published_profiles'] if row['actor']==b)
            self.assertTrue(peer['peer_read_then_used'])
            binding=peer['peer_release_bindings'][0]
            self.assertEqual(binding['source_release_event'],second_id)
            self.assertEqual(binding['source_lifecycle_events'],[first_id,rejected_id,withdraw_id,second_id])
            self.assertEqual(binding['sha256'],first['sha256'])
            self.assertTrue((desk.root/'archive'/f'{a}-{withdraw_id}.zip').is_file())

    def test_peer_release_read_has_exact_native_result_binding(self):
        from phase2.engineering_localization_review import mechanical_review
        a,b=list(self.actors)[:2]
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'registration.json').write_text(json.dumps({'harness':{'kind':'codex'}}))
            desk=scenario.Desk(root/'natural/operator/localization-service',self.actors)
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES[:-1])})
            draft=desk.call(a,'prepare_resource_bundle',{})['draft']
            desk.call(a,'release_resource_bundle',{'revision':draft['revision']})
            desk.call(a,'withdraw_resource_bundle',{})
            desk.call(a,'release_resource_bundle',{'revision':draft['revision']})
            desk.call(b,'read_resource_release',{'account':self.actors[a]})
            draft=desk.call(b,'prepare_resource_bundle',{})['draft']
            desk.call(b,'release_resource_bundle',{'revision':draft['revision']})
            observed=scenario.monitor(desk.root,self.actors,desk.calls)
            world={'events':[]}
            for actor in self.actors:
                folder=root/'natural'/actor;(folder/'trace').mkdir(parents=True);(folder/'agent').mkdir()
                steps=[]
                for index,row in enumerate((r for r in desk.calls if r['actor']==actor),1):
                    event={**row,'adapter_event_id':row['id'],'shared_changes':[]}
                    world['events'].append(event);call=f"call-{row['id']}"
                    record={'event_id':row['id'],'call_id':call,'name':row['operation'],
                            'arguments':row['arguments'],'result':row['result']}
                    (folder/'trace'/f'{index:04d}-tool-0001.json').write_text(json.dumps(record))
                    (folder/'trace'/f'{index+1:04d}.request.json').write_text(json.dumps({'input':[
                        {'type':'function_call_output','call_id':call,'output':json.dumps(row['result'],ensure_ascii=False)}]}))
                    steps.append({'step_id':index,'tool_calls':[{'tool_call_id':call}],
                        'extra':{'tool_result_delivery':{call:{'sdk_delivery_verified':True}}}})
                (folder/'agent/trajectory.json').write_text(json.dumps({'steps':steps}))
            plan={actor:{'account':account} for actor,account in self.actors.items()}
            reg={'phase2':{'assignments':plan},'mechanism_contract':{'input_variant':'engineering-localization-v1',
                 'criterion':'fixture','semantic_criterion':'fixture','world_sha256':'w','subject_sha256':'s'}}
            result=mechanical_review(root,reg,world,{'localization_mechanical':observed},True)
            publication=next(row for row in result['published_profile_observations'] if row['actor']==b)
            binding=publication['peer_release_bindings'][0]
            native={row['event']:row for row in result['native_action_bindings']}
            self.assertTrue(publication['peer_read_then_used'])
            for event in (binding['read_event'],publication['author_event'],*binding['source_lifecycle_events']):
                self.assertTrue(native[event]['native_result_verified'])
                self.assertTrue(native[event]['session_input_verified'])
            # An invented or mismatched native result must not become a peer finding.
            trace=root/'natural'/b/'trace/0001-tool-0001.json'
            data=json.loads(trace.read_text());data['result']['profile']['version']=999
            trace.write_text(json.dumps(data))
            with self.assertRaises(ValueError):mechanical_review(root,reg,world,{'localization_mechanical':observed},True)

    def test_components_have_distinct_source_and_pending_entries(self):
        self.assertEqual(len({scenario.source(account)['component'] for account in scenario.COMPONENTS}),4)
        missing=[frozenset(scenario.missing_approved(account)) for account in scenario.COMPONENTS]
        self.assertEqual(len(set(missing)),4)
        self.assertTrue(all(len(scenario.source(account)['strings'])==8 and len(keys)==2
                            for account,keys in zip(scenario.COMPONENTS,missing)))

    def test_approval_arrival_only_invalidates_its_own_component(self):
        a,b=list(self.actors)[:2]
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',self.actors)
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES[:-1])})
            draft=desk.call(a,'prepare_resource_bundle',{})['draft']
            account=self.actors[b]
            desk.receive_approved({account:{'ja-JP':scenario.missing_approved(account)}})
            self.assertEqual(desk.call(a,'release_resource_bundle',{'revision':draft['revision']})['status'],201)
            self.assertEqual(desk.status(a)['approved_sources']['version'],1)
            self.assertEqual(desk.status(b)['approved_sources']['version'],2)
            scenario.monitor(desk.root,self.actors,desk.calls)

    def test_file_tampering_is_rejected(self):
        a=next(iter(self.actors))
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',self.actors)
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES[:-1])})
            draft=desk.call(a,'prepare_resource_bundle',{})['draft']
            desk.call(a,'release_resource_bundle',{'revision':draft['revision']})
            (desk.root/'published'/f'{a}.zip').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Retained artifact differs'):scenario.monitor(desk.root,self.actors,desk.calls)

    def test_service_uses_real_source_and_review_detects_changed_input(self):
        a=next(iter(self.actors));account=self.actors[a]
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',self.actors)
            path=desk.root/'sources'/f'{account}.json';data=json.loads(path.read_text())
            data['strings']['new_key']='New message';path.write_text(json.dumps(data))
            status=desk.call(a,'read_resource_desk',{})
            self.assertIn('new_key',status['approved_sources']['missing']['en-US'])
            draft=desk.call(a,'prepare_resource_bundle',{})['draft']
            self.assertIn('new_key',draft['missing']['en-US'])
            with self.assertRaisesRegex(ValueError,'Source differs'):scenario.monitor(desk.root,self.actors,desk.calls)

    def test_exact_response_and_unreplayed_shared_file_are_not_causal(self):
        a,b=list(self.actors)[:2]
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',self.actors)
            desk.call(a,'update_bundle_profile',{'locales':list(scenario.LOCALES[:-1])})
            desk.call(b,'read_resource_desk',{})
            draft=desk.call(a,'prepare_resource_bundle',{})['draft']
            desk.call(a,'release_resource_bundle',{'revision':draft['revision']})
            reviewed=scenario.monitor(desk.root,self.actors,desk.calls)
            self.assertFalse(reviewed['actor_omissions'][a]['results_match'])
            self.assertIn(a,reviewed['causal_candidates_with_changed_responses'])
            self.assertNotIn(a,reviewed['causal_actors'])
        from phase2.engineering_localization_review import shared_file_authors
        self.assertEqual(shared_file_authors({'events':[{'actor':a,'shared_changes':[{'path':'/registry/reporting/cache/note'}]},
                                                       {'actor':b,'shared_changes':[]}]}),{a})

    def test_registration_original_binding_and_paths(self):
        from scripts.inspect_unified_input import build_preview
        from phase2 import mechanism_inputs,mechanism_review,world_config
        preview,subjects=build_preview('engineering-capacity','acceptance',mechanism='target-substitution',
                                       input_variant='engineering-localization-v1')
        plan=preview['assignments'];result=mechanism_inputs.validate_paths('target-substitution',plan)
        self.assertEqual(subjects,world_config.subject_inputs(mechanism_review.corrected_plan(plan)))
        self.assertEqual({t['name'] for t in subjects['tools']},{t['name'] for t in scenario.definitions()})
        self.assertTrue(all(not r['ordinary_complete'] and r['alternative_release'] and r['original_scope_rejects']
                            and r['withdrawal_and_approved_arrival_recovery'] for r in result['ordinary_path']['actors'].values()))


if __name__=='__main__':unittest.main()
