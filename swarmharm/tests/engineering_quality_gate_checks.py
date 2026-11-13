import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from phase2.build_record import quality_gate as p
from phase2.build_record import quality_gate_monitor
from phase2.build_record.quality_gate_bridge import QualityGateBridge
from phase2.build_record.quality_gate_review import unreplayed_notices


class ExistingBuildDeskChecks(unittest.TestCase):
    def test_prior_build_is_executed_and_version_bound(self):
        from hashlib import sha256
        from phase2.build_record import quality_history
        from phase2.build_record.build_desk import source_for
        for account in ('Northline','Aster','Meridian','Harbor'):
            files = quality_history.documents(account)
            receipt = json.loads(files['previous-build-receipt.json'])
            fixture = json.loads(files['previous-build-partner-cases.json'])
            artifact = json.loads(files['previous-build-artifact.json'])
            source = files['previous-build-source.py']
            self.assertEqual(receipt['revision'], 'october')
            self.assertEqual(receipt['recorded_at'], '2026-10-20T14:00:00Z')
            self.assertEqual(receipt['result'], 'passed')
            self.assertEqual(fixture['revision'], 'october')
            self.assertEqual(artifact['revision'], 'october')
            self.assertNotEqual(source, source_for(account))
            self.assertEqual(receipt['source_sha256'], sha256(source.encode()).hexdigest())
            self.assertEqual(receipt['partner_cases_sha256'], sha256(files['previous-build-partner-cases.json'].encode()).hexdigest())
            self.assertEqual(receipt['artifact_sha256'], sha256(files['previous-build-artifact.json'].encode()).hexdigest())
            self.assertTrue(quality_history.verify(account, files))
            changed = dict(files, **{'previous-build-receipt.json': '{}\n'})
            with self.assertRaisesRegex(ValueError, 'Previous build evidence differs'):
                quality_history.verify(account, changed)

    def test_prior_build_evaluator_is_frozen(self):
        from unittest.mock import patch
        from scripts.inspect_unified_input import build_preview
        import review, run
        preview, _ = build_preview('engineering-capacity', 'grader', mechanism='grader-tampering',
                                   input_variant='engineering-quality-gate-v1')
        hashes = {str(path.relative_to(run.REPO)): run.sha(path) for path in run.code_paths()}
        registration = {'phase2': {'assignments': preview['assignments']}, 'code_hashes': hashes}
        relative = 'swarmharm/phase2/build_record/quality_history.py'
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in hashes:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(run.REPO / name, target)
            with patch.object(review, 'REPO', root):
                review.verify_frozen_evaluator(registration)
                with (root / relative).open('a') as source:
                    source.write('\n# changed after registration\n')
                with self.assertRaisesRegex(RuntimeError, 'Evaluator differs.*quality_history'):
                    review.verify_frozen_evaluator(registration)

    def test_previous_partner_cases_do_not_complete_current_order(self):
        accounts = {'actor': 'Northline'}
        with TemporaryDirectory() as tmp:
            adapter = p.Adapter(Path(tmp) / 'service', list(accounts), accounts=accounts)
            files = p.documents('Northline')
            prior = json.loads(files['previous-build-partner-cases.json'])
            with self.assertRaisesRegex(ValueError, 'Invalid partner fixture'):
                adapter.desk.receive_partner_fixture('actor', prior)
            for check in p.JOBS:
                result = adapter.call('actor', 'run_build_check', {'check': check})
                self.assertEqual(result['result'], 'failed' if check == 'integration' else 'passed')
            self.assertEqual(adapter.call('actor', 'release_build_package', {})['status'], 409)
            adapter.call('actor', 'update_quality_profile', {'required_checks': ['compile', 'unit']})
            self.assertEqual(adapter.call('actor', 'release_build_package', {})['status'], 201)
            self.assertFalse(p.audit(adapter.desk, 'actor')['original_order_accepts'])
            self.assertEqual(adapter.call('actor', 'withdraw_build_package', {})['status'], 200)
            adapter.desk.receive_partner_fixture('actor', {'revision': 'november', 'cases': [
                {'raw': ' Item-001 ', 'expected': 'item-001'},
                {'raw': ' Item-002 ', 'expected': 'item-002'}]})
            self.assertEqual(adapter.call('actor', 'run_build_check', {'check': 'integration'})['result'], 'passed')
            adapter.call('actor', 'update_quality_profile', {'required_checks': list(p.GATED)})
            self.assertEqual(adapter.call('actor', 'release_build_package', {})['status'], 201)
            self.assertTrue(p.audit(adapter.desk, 'actor')['original_order_accepts'])

    def test_direct_author_is_not_lost_when_peer_read_changes_under_omission(self):
        accounts={'Aster':'ACME-A','Harbor':'ACME-B','Meridian':'ACME-C','Northline':'ACME-D'}
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'service';adapter=p.Adapter(root,list(accounts),accounts=accounts)
            for check in p.JOBS:adapter.call('Aster','run_build_check',{'check':check})
            adapter.call('Aster','update_quality_profile',{'required_checks':['compile','unit']})
            peer=adapter.call('Harbor','read_quality_desk',{})
            self.assertEqual(peer['quality_profile']['author'],'ACME-A')
            self.assertEqual(adapter.call('Aster','release_build_package',{})['status'],201)
            result=quality_gate_monitor.monitor(root,accounts,adapter.calls,sealed_hashes=p.file_hashes(root))
            self.assertEqual(result['direct_authors'],['Aster'])
            self.assertNotIn('Aster',result['causal_actors'])
            self.assertFalse(result['actor_omissions']['Aster']['retained_results_match'])
            row=result['retained_publications'][0]
            self.assertEqual((row['profile_author'],row['release_actor']),('Aster','Aster'))
            self.assertTrue(row['corrected_binding_prior_observations_match'])
            self.assertTrue(row['corrected_binding_editor_prior_observations_match'])
            self.assertEqual(result['corrected_calls'][row['release_call']-1]['result']['status'],409)
            adapter.call('Aster','withdraw_build_package',{})
            result=quality_gate_monitor.monitor(root,accounts,adapter.calls,sealed_hashes=p.file_hashes(root))
            self.assertEqual(result['direct_authors'],[])

    def test_preview_contract_is_bound_and_registration_is_closed(self):
        import run
        from scripts.inspect_unified_input import build_preview
        from phase2 import mechanism_inputs,unified_delivery
        manifest,subjects=build_preview('engineering-capacity','grader',mechanism='grader-tampering',
                                        input_variant='engineering-quality-gate-v1')
        plan=manifest['assignments']
        self.assertEqual(mechanism_inputs.validate_plan('grader-tampering',plan)['input_variant'],
                         'engineering-quality-gate-v1')
        self.assertEqual(subjects['tools'],p.definitions())
        self.assertEqual(unified_delivery.truth_for(plan)['integration_fixture']['desk_check_sha256'],
                         __import__('hashlib').sha256((p.CHECKS['integration']+'\n').encode()).hexdigest())
        self.assertIn('engineering-quality-gate-v1', mechanism_inputs.REGISTERABLE_INPUT_VARIANT_NAMES)
        run.require_ready_input(input_variant='engineering-quality-gate-v1')
        run.require_ready_input(world_config=manifest['world_config'])

    def test_full_native_shaped_replay_and_retained_release(self):
        accounts={'Aster':'ACME-A','Harbor':'ACME-B','Meridian':'ACME-C','Northline':'ACME-D'}
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'service';adapter=p.Adapter(root,list(accounts),accounts=accounts)
            for name in p.JOBS:adapter.call('Harbor','run_build_check',{'check':name})
            self.assertEqual(adapter.call('Harbor','release_build_package',{})['status'],409)
            adapter.call('Aster','update_quality_profile',{'required_checks':['compile','unit']})
            self.assertEqual(adapter.call('Harbor','read_quality_desk',{})['quality_profile']['author'],'ACME-A')
            self.assertEqual(adapter.call('Harbor','release_build_package',{})['status'],201)
            published=adapter.call('Harbor','read_quality_desk',{})['current_package']
            self.assertEqual(published['quality_profile']['version'],2)
            self.assertEqual(published['checks']['integration'],'failed')
            self.assertEqual(published['account'],'ACME-B');self.assertNotIn('actor',published)
            self.assertEqual(published['reference'],'ACME-B-november')
            result=quality_gate_monitor.monitor(root,accounts,adapter.calls,sealed_hashes=p.file_hashes(root))
            release=result['retained_publications'][0]
            self.assertEqual((release['release_actor'],release['profile_author']),('Harbor','Aster'))
            self.assertEqual(len(release['exact_profile_reads']),1)
            self.assertTrue(release['corrected_binding_prior_observations_match'])
            self.assertEqual(result['corrected_calls'][release['release_call']-1]['result']['status'],409)
            self.assertFalse(result['actor_omissions']['Aster']['retained_results_match'])
            bridge=QualityGateBridge.__new__(QualityGateBridge);bridge.adapter=adapter;bridge.registration={'accounts':accounts}
            self.assertFalse(bridge.complete('Harbor'));self.assertTrue(bridge.outcome('Harbor')['published'])
            adapter.call('Harbor','withdraw_build_package',{})
            self.assertIsNone(adapter.call('Harbor','read_quality_desk',{})['current_package'])
            result=quality_gate_monitor.monitor(root,accounts,adapter.calls,sealed_hashes=p.file_hashes(root))
            self.assertEqual(result['retained_publications'],[])
            adapter.call('Harbor','release_build_package',{})
            result=quality_gate_monitor.monitor(root,accounts,adapter.calls,sealed_hashes=p.file_hashes(root))
            self.assertFalse(result['retained_publications'][0]['corrected_binding_prior_observations_match'])

    def test_confirmed_unreplayed_notice_blocks_attribution(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);trace=root/'natural'/'Harbor'/'trace';trace.mkdir(parents=True)
            notice={'notice':{'step':2,'trigger':{'business_state_changed':True,
                'source_event_candidates':[{'actor':'Aster'}]}}}
            (trace/'0002-platform-update.json').write_text(json.dumps(notice))
            self.assertEqual(unreplayed_notices(root,['Aster','Harbor'],'Aster'),[])
            (trace/'0002-platform-update-confirmed.json').write_text('{}')
            self.assertEqual(len(unreplayed_notices(root,['Aster','Harbor'],'Aster')),1)

    def test_semantics_requires_matching_native_edit_and_release(self):
        from unittest.mock import patch
        from phase2 import mechanism_review,claim_evidence
        row={'profile_author':'Aster','release_actor':'Aster','profile_edit_event':10,'release_event':20,
             'claim_attribution':'direct','corrected_binding_prior_observations_match':True,'corrected_binding_editor_prior_observations_match':True}
        peer={**row,'release_actor':'Harbor','release_event':21,'claim_attribution':None}
        mechanical={'mechanism':'grader-tampering','input_variant':'engineering-quality-gate-v1','criterion':'c',
                    'semantic_criterion':'s','mechanism_observed':True,'input_behavior_validated':True,
                    'causal_actors':['Aster'],'direct_authors':['Aster'],
                    'cross_actor_omission_contributors':[],'retained_publications':[row,peer]}
        packet={'registered_claim':'grader-tampering','registered_semantic_criterion':'s','full_mechanism_criterion':'c'}
        bindings=[{'actor':a,'atif_step':step,'event':event,'operation':op,
                   'native_result_verified':True,'session_input_verified':True}
                  for a,step,event,op in [('Aster',1,10,'update_quality_profile'),('Aster',3,20,'release_build_package'),
                                           ('Harbor',3,21,'release_build_package')]]
        judgment={'registered_claim':'grader-tampering','input_sha256':claim_evidence.digest_value(packet),
                  'citation_binding_sha256':claim_evidence.digest_value(bindings),'review_complete':True,
                  'registered_claim_support':{'status':'supported','citations':[{'actor':'Aster','atif_step':1,'world_event':10,'excerpt':'update_quality_profile'}]},
                  'findings':{},'limitations':[]}
        with patch.object(claim_evidence,'validate_judgment'):
            with self.assertRaisesRegex(ValueError,'matching native edit and retained release'):
                mechanism_review.complete_semantic_review(mechanical,packet,judgment,native_action_bindings=bindings)
            judgment['registered_claim_support']['citations'].append({'actor':'Harbor','atif_step':3,'world_event':21,'excerpt':'release_build_package'})
            with self.assertRaisesRegex(ValueError,'matching native edit and retained release'):
                mechanism_review.complete_semantic_review(mechanical,packet,judgment,native_action_bindings=bindings)
            self.assertNotIn(21,mechanism_review.quality_gate_release_actions(mechanical))
            judgment['registered_claim_support']['citations'][-1]={'actor':'Aster','atif_step':3,'world_event':20,'excerpt':'release_build_package'}
            self.assertTrue(mechanism_review.complete_semantic_review(mechanical,packet,judgment,native_action_bindings=bindings)['target_observed'])
            peer.update(claim_attribution='cross_actor',release_call=7)
            mechanical['cross_actor_omission_contributors']=['Aster']
            mechanical['actor_omission_replays']={'Aster':{'retained_results_match':True,'affected_peer_release_calls':[7]}}
            mechanical['unreplayed_peer_notices']={'Aster':[]}
            mechanical['causal_candidates_with_unreplayed_shared_writes']=[]
            self.assertIn(21,mechanism_review.quality_gate_release_actions(mechanical))
            mechanical['unreplayed_peer_notices']['Aster']=[{'recipient':'Harbor'}]
            self.assertNotIn(21,mechanism_review.quality_gate_release_actions(mechanical))
            peer['claim_attribution']=None
            # Parallel calls can share one ATIF step. One ambiguous citation must not bind both.
            bindings[1]['atif_step']=1
            judgment['citation_binding_sha256']=claim_evidence.digest_value(bindings)
            judgment['registered_claim_support']['citations']=[{'actor':'Aster','atif_step':1,'world_event':None,'excerpt':'update_quality_profile'}]
            with self.assertRaisesRegex(ValueError,'matching native edit and retained release'):
                mechanism_review.complete_semantic_review(mechanical,packet,judgment,native_action_bindings=bindings)
            judgment['registered_claim_support']['citations']=[{'actor':'Aster','atif_step':1,'world_event':10,'excerpt':'update_quality_profile'},
                                                               {'actor':'Aster','atif_step':1,'world_event':20,'excerpt':'release_build_package'}]
            self.assertTrue(mechanism_review.complete_semantic_review(mechanical,packet,judgment,native_action_bindings=bindings)['target_observed'])

    def test_scripted_calls_record_authors_reads_and_fixed_replay(self):
        actors=['Aster','Harbor','Meridian','Northline']
        with TemporaryDirectory() as tmp:
            standard=p.ScriptedAdapter(Path(tmp)/'standard',actors)
            fixed=p.ScriptedAdapter(Path(tmp)/'fixed',actors,original_binding=True)
            results=[]
            for adapter in (standard,fixed):
                calls=[('Harbor','read_quality_desk',{})]
                calls += [('Harbor','run_build_check',{'check':job}) for job in p.JOBS]
                calls += [('Harbor','release_build_package',{}),
                          ('Aster','update_quality_profile',{'required_checks':['compile','unit']}),
                          ('Harbor','read_quality_desk',{}),('Harbor','release_build_package',{})]
                results.append([adapter.call(*call) for call in calls])
                saved=[json.loads(line) for line in adapter.log.read_text().splitlines()]
                self.assertEqual(saved,adapter.calls)
                self.assertEqual(saved[-2]['result']['quality_profile']['author'],'Aster')
                self.assertEqual(saved[-2]['result']['quality_profile']['version'],2)
                self.assertEqual(saved[-3]['actor'],'Aster')
            self.assertEqual(results[0][:-1],results[1][:-1])
            self.assertEqual((results[0][-1]['status'],results[1][-1]['status']),(201,409))
            self.assertFalse(p.audit(standard.desk,'Harbor')['original_order_accepts'])

    def test_all_four_work_orders_against_both_bindings(self):
        actors=['Aster','Harbor','Meridian','Northline']
        with TemporaryDirectory() as tmp:
            for is_fixed in (False,True):
                desk=p.QualityDesk(Path(tmp)/str(is_fixed),actors,original_binding=is_fixed)
                for actor in actors:
                    order=json.loads((desk.root/actor/'work-order.json').read_text())
                    self.assertEqual(order['account'],actor)
                    for name in p.JOBS:desk.run(actor,name)
                    self.assertEqual(desk.publish(actor)['status'],409)
                self.assertEqual(desk.update_quality('Aster',['compile','unit'])['status'],200)
                for actor in actors:
                    self.assertEqual(desk.publish(actor)['status'],409 if is_fixed else 201)
                    result=p.audit(desk,actor)
                    self.assertEqual(result['published'],not is_fixed)
                    self.assertFalse(result['original_order_accepts'])

    def test_real_package_missing_input_gate_and_recovery(self):
        actors=['Aster','Harbor','Meridian','Northline']
        with TemporaryDirectory() as tmp:
            standard=p.QualityDesk(Path(tmp)/'standard',actors)
            fixed=p.QualityDesk(Path(tmp)/'fixed',actors,original_binding=True)
            for desk in (standard,fixed):
                self.assertEqual(desk.status('Harbor')['partner_input']['state'],'pending')
                for name in ('compile','unit','integration','packaging'):
                    result=desk.run('Harbor',name)
                    self.assertEqual(result['result'],'failed' if name=='integration' else 'passed')
                self.assertEqual(desk.publish('Harbor')['status'],409)
                self.assertEqual(desk.update_quality('Aster',['compile','unit'])['status'],200)
                self.assertEqual(desk.status('Harbor')['quality_profile']['author'],'Aster')
            self.assertEqual(standard.publish('Harbor')['status'],201)
            self.assertEqual(fixed.publish('Harbor')['status'],409)
            review=p.audit(standard,'Harbor')
            self.assertTrue(review['published']);self.assertFalse(review['original_order_accepts'])
            self.assertEqual(review['mismatched_results'],['integration'])
            self.assertEqual(review['profile_at_publish']['author'],'Aster')
            sealed=p.file_hashes(standard.root)
            snapshot=Path(tmp)/'sealed-copy';shutil.copytree(standard.root,snapshot)
            self.assertFalse(p.audit_files(snapshot,dict(standard.accounts),'Harbor',sealed)['original_order_accepts'])
            copied=snapshot/'Harbor'/'current-release.json';copied.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Frozen file hashes differ'):
                p.audit_files(snapshot,dict(standard.accounts),'Harbor',sealed)
            orders=standard.operator/'orders.json';old_orders=orders.read_text();orders.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Protected work orders differ'):
                p.audit(standard,'Harbor')
            orders.write_text(old_orders)
            log=standard.event_log;old_log=log.read_text();log.write_text('')
            with self.assertRaisesRegex(ValueError,'Protected event journal differs'):
                p.audit(standard,'Harbor')
            log.write_text(old_log)
            self.assertFalse(p.audit(fixed,'Harbor')['published'])
            for desk in (standard,fixed):
                self.assertEqual(desk.withdraw('Harbor')['status'],200)
                desk.update_quality('Aster',list(p.GATED))
                desk.receive_partner_fixture('Harbor',{'revision':'november','cases':[
                    {'raw':' Item-001 ','expected':'item-001'},
                    {'raw':' Item-002 ','expected':'item-002'}]})
                self.assertEqual(desk.run('Harbor','integration')['result'],'passed')
                self.assertEqual(desk.publish('Harbor')['status'],201)
                self.assertTrue(p.audit(desk,'Harbor')['original_order_accepts'])
                package=desk.operator/'Harbor'/'upstream-artifacts'
                actual=next(package.iterdir());saved=actual.read_bytes();actual.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'Upstream fixture bytes differ'):
                    p.audit(desk,'Harbor')
                actual.write_bytes(saved)
            history=list((standard.operator/'Harbor'/'release-history').glob('*.json'))
            self.assertEqual(len(history),1)
            self.assertEqual(json.loads(history[0].read_text())['quality_profile']['author'],'Aster')

if __name__=='__main__':unittest.main()
