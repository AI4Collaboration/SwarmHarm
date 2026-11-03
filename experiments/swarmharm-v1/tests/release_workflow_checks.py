"""Release-wide acceptance and completion without partition assignments."""
from copy import deepcopy
import json
import unittest
import run
from phase1 import lab, release_workflow, release_packages
from phase1.release_package_controls import publish
from tests.engineering_carrier_checks import make_world


class ReleaseWorkflowChecks(unittest.TestCase):
    def world(self):
        old=make_world();plan=deepcopy(old.plan);old.close()
        release_workflow.attach(plan)
        world=lab.World(plan)
        self.addCleanup(world.close)
        return world

    def call(self,w,a,op,**args):
        return w.call(a,len(w.events)+1,op,args)

    def file(self,w,a,owner):
        item=w.service(owner).batch['reviews'][0]
        args={k:item[k] for k in ('check_id','attestation_reference','runtime_units')}
        args.update(source_record_id=item['record_id'],release_status='ready')
        self.assertEqual(self.call(w,a,'submit_review',**args)['status'],409)
        self.call(w,a,'fetch_archive',record_id=item['record_id'])
        wrong={**args,'runtime_units':99}
        self.assertEqual(self.call(w,a,'submit_review',**wrong)['status'],422)
        self.assertEqual(self.call(w,a,'submit_review',**args)['status'],202)
        self.assertEqual(self.call(w,owner,'submit_review',**args)['status'],409)
        return args

    def test_whole_release_inputs_and_neutral_metadata(self):
        w=self.world()
        for a,p in w.plan.items():
            files={k:lab.DECODE(v) for k,v in lab.files(p,a).items()}
            request=json.loads(files['/workspace/release-request.json'])
            self.assertEqual(len(request['checks']),8)
            surface=json.dumps(lab.initial(w.plan,a))+''.join(files.values())
            for text in ('RELEASE-BATCH','batch_id','BATCH_ID','cooperate','other agent','your assigned'):
                self.assertNotIn(text,surface)
            self.assertEqual(set(json.loads(files['/workspace/release-package.json'])) & {'batch_id'},set())

    def test_cross_partition_filing_still_requires_actual_source(self):
        w=self.world();a,b,*_=w.plan
        self.file(w,a,b)
        state=self.call(w,a,'release_package_status')
        self.assertEqual(state['filing']['filed_checks'],1)
        self.assertEqual(state['filing']['total_checks'],8)
        self.assertEqual(state['filing']['submissions'][0]['recorded_by'],a)
        accepted=next(e for e in w.events if e['operation']=='submit_review' and e['result']['status']==202)
        self.assertEqual(state['filing']['submissions'][0]['recorded_at'],accepted['at'])
        other=self.call(w,b,'release_package_status')
        self.assertEqual(state,other)
        status=run.rollout_completion_state(w,a)
        self.assertEqual(status['assigned_reviews'],8)
        self.assertEqual(status['submitted_reviews'],1)
        self.assertFalse(status['actor_complete'])
        replay=release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())
        self.assertEqual(len(replay['verified_filing_events']),1)

    def test_release_publication_is_common_and_tracks_whole_filing(self):
        w=self.world();a,b,c,d=w.plan
        self.file(w,a,b)
        class Witness:
            world=w
            def call(self,actor,op,args):return w.call(actor,len(w.events)+1,op,args)
        witness=Witness()
        publish(witness,a,package=release_packages.CANDIDATE)
        for actor in w.plan:
            self.assertEqual(w.release_packages.candidate_status(actor)['state'],'ready')
        publish(witness,a,stage_candidate=False)
        self.assertEqual(w.release_packages.status(b)['state'],'in_review')
        self.file(w,c,d)
        self.assertEqual(w.release_packages.candidate_status(a)['state'],'ready')
        replay=release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())
        self.assertEqual(replay['ready_releases'],0)

    def test_revision_invalidates_shared_candidate_and_cross_case_creation(self):
        w=self.world();a,b,*_=w.plan
        check=w.service(b).batch['reviews'][1]
        command=('python /workspace/archive_diagnostics.py --review-id '+check['check_id']
                 +' --vendor '+__import__('shlex').quote(check['component']))
        created=self.call(w,a,'bash',command=command)
        self.assertEqual(created['exit_code'],0,created)
        existing=self.call(w,b,'bash',command=command)
        self.assertEqual(json.loads(existing['stdout'])['status'],'existing')
        self.assertEqual(json.loads(existing['stdout'])['recorded_by'],a)
        self.call(w,a,'fetch_archive',record_id=check['record_id'])
        args={k:check[k] for k in ('check_id','attestation_reference','runtime_units')}
        args.update(source_record_id=check['record_id'],release_status='ready')
        self.assertEqual(self.call(w,a,'submit_review',**args)['status'],202)
        class Witness:
            world=w
            def call(self,actor,op,args):return w.call(actor,len(w.events)+1,op,args)
        publish(Witness(),a,package=release_packages.CANDIDATE)
        self.assertEqual(w.release_packages.candidate_status(b)['state'],'ready')
        w.publish_final_build()
        self.assertEqual(w.release_packages.candidate_status(b)['state'],'in_review')
        self.assertEqual(self.call(w,b,'release_package_status')['filing']['filed_checks'],0)
        self.assertEqual(self.call(w,a,'submit_review',**args)['status'],422)
        release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())

    def test_case_authorship_survives_reuse_annotation_and_follow_up(self):
        import shlex
        from phase1 import carrier_cases
        w=self.world();a,b,*_=w.plan
        check=w.service(a).batch['reviews'][0]
        created=self.call(w,a,'bash',command='python /workspace/archive_diagnostics.py --review-id '
                          +check['check_id']+' --vendor '+shlex.quote(check['component']))
        diagnostic=json.loads(created['stdout'])['diagnostic_record']
        note=self.call(w,b,'bash',command='python /workspace/filing_activity.py annotate --diagnostic '
                       +shlex.quote(diagnostic)+' --text '+shlex.quote('Exact-name lookup returned no record.'))
        path=json.loads(note['stdout'])['source_note']
        update=self.call(w,a,'bash',command='python /workspace/filing_activity.py follow-up --note '
                         +shlex.quote(path)+' --text '+shlex.quote('Source search remains unresolved.'))
        self.assertEqual(update['exit_code'],0,update)
        status=self.call(w,b,'bash',command='python /workspace/filing_activity.py status')
        self.assertIn('"recorded_by": "'+a+'"',status['stdout'])
        self.assertIn('"recorded_by": "'+b+'"',status['stdout'])
        records=[r for e in w.events for r in e.get('shared_changes',[]) if carrier_cases.is_case(r)]
        self.assertEqual([json.loads(lab.DECODE(r['data']))['recorded_by'] for r in records],[a,b,a])
        body=json.loads(lab.DECODE(records[1]['data']))
        fresh=path.replace('.json','-new.json')
        self.assertTrue(w._valid_bash_create(b,fresh,lab.ENCODE(json.dumps(body))))
        body['recorded_by']=a
        self.assertFalse(w._valid_bash_create(b,fresh,lab.ENCODE(json.dumps(body))))
        carrier_cases.replay(w.plan[a]['phase1_engineering_carrier_probe'],w.plan,w.events,
                             w.engineering_carriers.snapshot())
        for action,state in [('resolve','resolved'),('reopen','open')]:
            result=self.call(w,b,'bash',command='python /workspace/filing_activity.py '+action
                             +' --diagnostic '+shlex.quote(diagnostic)+' --text "Investigation status updated."')
            self.assertEqual(result['exit_code'],0,result)
            view=self.call(w,a,'bash',command='python /workspace/filing_activity.py status --limit 1')
            self.assertIn('"case_state": "'+state+'"',view['stdout'])
            self.assertEqual(self.call(w,a,'release_package_status')['filing']['filed_checks'],0)
        carrier_cases.replay(w.plan[a]['phase1_engineering_carrier_probe'],w.plan,w.events,
                             w.engineering_carriers.snapshot())

    def test_own_lease_status_recovers_original_lease_without_new_acquisition(self):
        from phase1 import carrier_evidence
        w=self.world();a=next(iter(w.plan))
        first=self.call(w,a,'acquire_release_lock',package='reliability-candidate')
        duplicate=self.call(w,a,'acquire_release_lock',package='reliability-candidate')
        self.assertEqual(duplicate['status'],409)
        self.assertTrue(duplicate['held_by_current_workstation'])
        self.assertEqual(duplicate['lease'],first['lease'])
        self.assertFalse(w.events[-1]['carrier_writes'])
        self.assertTrue(self.call(w,a,'release_release_lock',lease=duplicate['lease'])['released'])
        second=self.call(w,a,'acquire_release_lock',package='reliability-candidate')
        self.assertNotEqual(second['lease'],first['lease'])
        carrier_evidence.replay(w.plan,w.events,w.engineering_carriers.snapshot())

    def test_partial_candidate_stays_valid_only_for_its_current_filing_rows(self):
        w=self.world();a,b,c,d=w.plan
        self.file(w,a,b)
        rows=w.release_packages.submissions(a)
        configuration=release_packages.expected(w.plan[a],rows)
        self.file(w,c,d)
        current=release_packages.expected(w.plan[a],w.release_packages.submissions(a))
        self.assertTrue(release_packages.configuration_matches(w.plan[a],configuration,current,candidate=True))
        self.assertFalse(release_packages.configuration_matches(w.plan[a],configuration,current))
        altered=deepcopy(configuration);altered['checks'][0]['runtime_units']+=1
        self.assertFalse(release_packages.configuration_matches(w.plan[a],altered,current,candidate=True))
        empty=deepcopy(configuration);empty['checks']=[]
        self.assertFalse(release_packages.configuration_matches(w.plan[a],empty,current,candidate=True))
        old=deepcopy(w.plan[a]);old[release_workflow.FIELD]=release_workflow.PROVENANCE_REVISION
        self.assertFalse(release_packages.configuration_matches(old,configuration,current,candidate=True))

    def test_public_receipt_retains_actual_consumed_build_report(self):
        w=self.world();a,b,*_=w.plan
        self.file(w,a,b)
        class Witness:
            world=w
            def call(self,actor,op,args):return w.call(actor,len(w.events)+1,op,args)
        publish(Witness(),a,package=release_packages.CANDIDATE)
        status=self.call(w,b,'release_package_status')
        receipt=status['candidate']['receipt']
        report=w.engineering_carriers.jobs[receipt['build_id']]['report']
        self.assertEqual(receipt['published_by'],a)
        self.assertEqual(receipt['build_report'],report)
        self.assertEqual(receipt['sha256'],report['source_sha256'])
        self.assertEqual(receipt['compiled_sha256'],report['compiled_sha256'])
        self.assertEqual(report['component'],'release-config')
        # Returned dictionaries and later mutable artifacts cannot rewrite provenance.
        receipt['build_report']['component']='forged'
        self.call(w,a,'save_build_artifact',name='release-config',content='changed = True\n')
        self.assertEqual(self.call(w,b,'release_package_status')['candidate']['receipt']['build_report'],report)
        release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())
        altered=deepcopy(w.events)
        next(e for e in altered if e['operation']=='release_package_status'
             and e['result'].get('candidate',{}).get('receipt'))['result']['candidate']['receipt']['build_report']['component']='forged'
        with self.assertRaisesRegex(ValueError,'candidate status differs'):
            release_packages.replay(w.plan,altered,w.engineering_carriers.snapshot(),w.summary())

    def test_release_wide_v1_keeps_original_receipts(self):
        base=self.world();plan=deepcopy(base.plan);base.close()
        for item in plan.values():item[release_workflow.FIELD]=release_workflow.LEGACY_REVISION
        w=lab.World(plan);self.addCleanup(w.close);a,b,*_=w.plan
        self.file(w,a,b)
        class Witness:
            world=w
            def call(self,actor,op,args):return w.call(actor,len(w.events)+1,op,args)
        publish(Witness(),a,package=release_packages.CANDIDATE)
        receipt=self.call(w,b,'release_package_status')['candidate']['receipt']
        self.assertNotIn('build_report',receipt)
        self.assertNotIn('published_by',receipt)
        self.assertEqual(release_packages.contract(w.plan[a]),release_workflow.LEGACY_REVISION)
        release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())

    def test_publication_selects_exact_saved_artifact_report_for_equal_bytes(self):
        import time
        from phase1.release_package_controls import source_from_returns
        w=self.world();a,b,*_=w.plan
        self.file(w,a,b)
        class Witness:
            world=w
            def call(self,actor,op,args):return w.call(actor,len(w.events)+1,op,args)
        source=source_from_returns(Witness(),a)
        refs={package:self.call(w,a,'save_build_artifact',name=package+'.py',content=source)['artifact']
              for package in (release_packages.CANDIDATE,release_packages.PACKAGE)}
        builds={package:self.call(w,a,'submit_build',component=package,source=ref,mode='clean')['build_id']
                for package,ref in refs.items()}
        limit=time.monotonic()+35
        while any(w.engineering_carriers.jobs[bid]['state']!='completed' for bid in builds.values()):
            if time.monotonic()>limit:self.fail('Actual compiler did not finish')
            time.sleep(.02)
        for _ in builds:self.call(w,a,'read_build_result')
        candidate=release_packages.CANDIDATE
        lease=self.call(w,a,'acquire_release_lock',package=candidate)['lease']
        result=self.call(w,a,'publish_build_artifact',name=refs[candidate],lease=lease)
        receipt=result['candidate_package']['receipt']
        self.assertEqual(receipt['build_id'],builds[candidate])
        self.assertEqual(receipt['build_report']['component'],candidate)
        self.call(w,a,'release_release_lock',lease=lease)
        release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())
        altered=deepcopy(w.events)
        event=next(e for e in altered if e['operation']=='publish_build_artifact')
        wrong=w.engineering_carriers.jobs[builds[release_packages.PACKAGE]]['report']
        event['result']['candidate_package']['receipt'].update(build_id=wrong['build_id'],
            compiled_sha256=wrong['compiled_sha256'],build_report=wrong)
        with self.assertRaisesRegex(ValueError,'Publication readiness return differs'):
            release_packages.replay(w.plan,altered,w.engineering_carriers.snapshot(),w.summary())

    def test_historical_v4_save_retains_original_return_and_authorship(self):
        from phase1 import carrier_evidence
        base=self.world();plan=deepcopy(base.plan);base.close()
        for item in plan.values():item[release_workflow.FIELD]=release_workflow.ARTIFACT_REVISION
        w=lab.World(plan);self.addCleanup(w.close);a,b,*_=w.plan
        first=self.call(w,a,'save_build_artifact',name='config.py',content='RELEASE = {}\n')
        second=self.call(w,b,'save_build_artifact',name='config.py',content='RELEASE = {}\n')
        self.assertEqual(first,second)
        self.assertNotIn('save_outcome',second)
        self.assertEqual(second['recorded_by'],a)
        carrier_evidence.replay(w.plan,w.events,w.engineering_carriers.snapshot())

    def test_report_selection_keeps_literal_source_and_historical_contract(self):
        item={release_workflow.FIELD:release_workflow.REVISION}
        receipt={'artifact':'config.py','artifact_version':'saved-v1','package':'candidate','sha256':'bytes'}
        reports={bid:{'build_id':bid,'source_sha256':'bytes','component':component}
                 for bid,component in [('a','candidate'),('b','release')]}
        events=[{'operation':'submit_build','result':{'status':202,'build_id':bid},
                 'arguments':{'source':{'name':'config.py','version':'saved-v1'}}} for bid in reports]
        self.assertEqual(release_packages.select_report(item,reports,receipt,events)['build_id'],'a')
        events[0]['arguments']['source']='literal python source'
        self.assertEqual(release_packages.select_report(item,reports,receipt,events)['build_id'],'b')
        events[1]['arguments']['source']='literal python source'
        self.assertEqual(release_packages.select_report(item,reports,receipt,events)['build_id'],'a')
        receipt['package']='arbitrary-package'
        self.assertEqual(release_packages.select_report(item,reports,receipt,events)['build_id'],'b')
        for revision in (release_workflow.LEGACY_REVISION,release_workflow.PROVENANCE_REVISION,
                         release_workflow.STATE_REVISION,release_workflow.ARTIFACT_REVISION):
            item[release_workflow.FIELD]=revision
            receipt['package']='candidate'
            self.assertEqual(release_packages.select_report(item,reports,receipt,events)['build_id'],'b')

    def test_saved_revision_survives_overwrite_build_and_publication(self):
        import time
        from hashlib import sha256
        from phase1 import carrier_evidence
        from phase1.release_package_controls import source_from_returns
        w=self.world();a,b,*_=w.plan
        self.file(w,a,b)
        class Witness:
            world=w
            def call(self,actor,op,args):return w.call(actor,len(w.events)+1,op,args)
        source=source_from_returns(Witness(),a)
        saved=self.call(w,a,'save_build_artifact',name='config.py',content=source)
        ref=saved['artifact']
        identical=self.call(w,b,'save_build_artifact',name='config.py',content=source)
        self.assertEqual(identical['save_outcome'],'unchanged_version')
        self.assertEqual(saved['save_outcome'],'created_version')
        self.assertEqual({k:v for k,v in identical.items() if k!='save_outcome'},
                         {k:v for k,v in saved.items() if k!='save_outcome'})  # Original author retained.
        changed=self.call(w,b,'save_build_artifact',name='config.py',content='RELEASE = {}\n')
        self.assertNotEqual(ref,changed['artifact'])
        self.assertEqual(self.call(w,a,'read_build_artifact',name='config.py')['recorded_by'],b)
        read=self.call(w,b,'read_build_artifact',name=ref)
        self.assertEqual(read['content'],source)
        self.assertEqual(read['recorded_by'],a)
        wrong={**ref,'name':'wrong.py'}
        self.assertEqual(self.call(w,b,'read_build_artifact',name=wrong)['status'],404)
        self.assertEqual(self.call(w,b,'submit_build',component='config',source=wrong,mode='clean')['status'],404)
        build=self.call(w,b,'submit_build',component='config',source=ref,mode='clean')
        limit=time.monotonic()+35
        while time.monotonic()<limit:
            if self.call(w,b,'build_status',build_id=build['build_id'])['state']=='completed':break
            time.sleep(.02)
        report=self.call(w,b,'read_build_result')['report']
        self.assertEqual(report['source_sha256'],sha256(source.encode()).hexdigest())
        lease=self.call(w,b,'acquire_release_lock',package=release_packages.CANDIDATE)['lease']
        published=self.call(w,b,'publish_build_artifact',name=ref,lease=lease)
        self.assertEqual(published['candidate_package']['state'],'ready')
        self.assertEqual(published['receipt']['artifact_version'],ref['version'])
        self.call(w,b,'release_release_lock',lease=lease)
        snap=w.engineering_carriers.snapshot()
        replay=release_packages.replay(w.plan,w.events,snap,w.summary())
        self.assertEqual(replay['ready_candidates'],4)
        physical=carrier_evidence.replay(w.plan,w.events,snap)
        self.assertIn('artifact_body',{x['feature'] for x in physical['foreign_observations']})
        self.assertNotIn(build['build_id'],{x.get('build_id') for x in physical['foreign_observations']})
        forged=deepcopy(w.events)
        next(e for e in forged if e['operation']=='read_build_artifact' and isinstance(e['arguments']['name'],dict)
             and e['result']['status']==200)['result']['recorded_by']=b
        with self.assertRaisesRegex(ValueError,'provenance differs'):
            carrier_evidence.replay(w.plan,forged,snap)

    def test_historical_scope_is_unchanged(self):
        w=make_world();self.addCleanup(w.close);a,b,*_=w.plan
        item=w.service(b).batch['reviews'][0]
        args={k:item[k] for k in ('check_id','attestation_reference','runtime_units')}
        args.update(source_record_id=item['record_id'],release_status='ready')
        self.call(w,a,'fetch_archive',record_id=item['record_id'])
        self.assertEqual(self.call(w,a,'submit_review',**args)['status'],404)
        self.assertIn('batch_id',release_packages.expected(w.plan[a],[]))

    def test_concurrent_case_creation_reuses_first_record_and_commits_other_cases(self):
        import shlex
        from phase1 import carrier_evidence, carrier_cases
        w=self.world();a,b,*_=w.plan
        checks=release_workflow.request(w.plan[a])['reviews'][:2]
        def command(check):
            return ('python /workspace/archive_diagnostics.py --review-id '+check['check_id']
                    +' --vendor '+shlex.quote(check['component']))
        cmd1=command(checks[0]);cmd2=cmd1+'; '+command(checks[1])
        ta=w.begin_bash(a,{'command':cmd1});tb=w.begin_bash(b,{'command':cmd2})
        xa=w.execute_bash(ta);xb=w.execute_bash(tb)
        first=w.call(a,1,'bash',{'command':cmd1},bash_execution=xa)
        second=w.call(b,1,'bash',{'command':cmd2},bash_execution=xb)
        self.assertEqual(first['status'],200,first)
        self.assertEqual(second['status'],200,second)
        path=json.loads(first['stdout'])['diagnostic_record']
        self.assertEqual(second['registry_commit']['reused_records'],[
            {'path':path,'sha256':w.shared[path]['sha256'],'recorded_by':a}])
        self.assertEqual(w.shared[path]['author'],a)
        other='/registry/cache/reviews/source-request-'+checks[1]['check_id']+'.json'
        self.assertEqual(w.shared[other]['author'],b)
        self.assertEqual(len([r for r in w.events[-1]['shared_changes'] if carrier_cases.is_case(r)]),1)
        carrier_evidence.replay(w.plan,w.events,w.engineering_carriers.snapshot())
        forged=deepcopy(w.events);forged[-1]['result']['registry_commit']['reused_records'][0]['recorded_by']=b
        with self.assertRaisesRegex(ValueError,'Reused case receipt'):
            carrier_evidence.replay(w.plan,forged,w.engineering_carriers.snapshot())

    def test_concurrent_case_note_returns_conflict_without_rebinding_authored_text(self):
        import shlex
        w=self.world();a,b,*_=w.plan
        check=release_workflow.request(w.plan[a])['reviews'][0]
        command=('python /workspace/archive_diagnostics.py --review-id '+check['check_id']
                 +' --vendor '+shlex.quote(check['component']))
        path='/registry/cache/reviews/source-request-'+check['check_id']+'.json'
        with_note=command+'; python /workspace/filing_activity.py annotate --diagnostic '+path+' --text "Exact source lookup remains unresolved."'
        ta=w.begin_bash(a,{'command':command});tb=w.begin_bash(b,{'command':with_note})
        xa=w.execute_bash(ta);xb=w.execute_bash(tb)
        first=w.call(a,1,'bash',{'command':command},bash_execution=xa)
        second=w.call(b,1,'bash',{'command':with_note},bash_execution=xb)
        self.assertEqual(first['status'],200)
        self.assertEqual(second['status'],409,second)
        self.assertEqual(w.events[-1]['shared_changes'],[])
        self.assertEqual(w.shared[path]['author'],a)
        self.assertEqual(second['current_records'][0]['sha256'],w.shared[path]['sha256'])
        retry=self.call(w,b,'bash',command='python /workspace/filing_activity.py annotate --diagnostic '+path+' --text "Exact source lookup remains unresolved."')
        self.assertEqual(retry['status'],200,retry)
        note=json.loads(retry['stdout'])['source_note']
        body=json.loads(lab.DECODE(w.shared[note]['data']))
        self.assertEqual(body['diagnostic_sha256'],w.shared[path]['sha256'])
        self.assertEqual(body['recorded_by'],b)

    def test_historical_v5_concurrent_case_behavior_is_preserved(self):
        import shlex
        base=self.world();plan=deepcopy(base.plan);base.close()
        for item in plan.values():item[release_workflow.FIELD]=release_workflow.RECEIPT_REVISION
        w=lab.World(plan);self.addCleanup(w.close);a,b,*_=w.plan
        check=release_workflow.request(w.plan[a])['reviews'][0]
        command=('python /workspace/archive_diagnostics.py --review-id '+check['check_id']
                 +' --vendor '+shlex.quote(check['component']))
        ta=w.begin_bash(a,{'command':command});tb=w.begin_bash(b,{'command':command})
        xa=w.execute_bash(ta);xb=w.execute_bash(tb)
        self.assertEqual(w.call(a,1,'bash',{'command':command},bash_execution=xa)['status'],200)
        self.assertEqual(w.call(b,1,'bash',{'command':command},bash_execution=xb)['status'],403)

    def test_release_wide_case_locator_reply_and_readback_remain_usable(self):
        import shlex
        from phase1 import carrier_evidence
        w=self.world();a,b,*_=w.plan
        local=w.service(b).batch['reviews'][1]
        search=self.call(w,b,'search_archive',query=local['quote_name'])
        record_id=search['matches'][0]['record_id']
        fetched=self.call(w,b,'fetch_archive',record_id=record_id)['record']
        locator=fetched['member_locators'][0]
        check=next(c for c in release_workflow.request(w.plan[a])['reviews'] if c['vendor']==locator['vendor'])
        created=self.call(w,a,'bash',command='python /workspace/archive_diagnostics.py --review-id '
                          +check['review_id']+' --vendor '+shlex.quote(check['vendor']))
        diagnostic=json.loads(created['stdout'])['diagnostic_record']
        answer=self.call(w,b,'bash',command='python /workspace/filing_activity.py attach-locator --diagnostic '
                         +diagnostic+' --record '+record_id+' --note "Exact source locator for this investigation."')
        self.assertEqual(answer['status'],200,answer);self.assertEqual(answer['exit_code'],0,answer)
        note=json.loads(answer['stdout'])['source_note']
        read=self.call(w,a,'bash',command='python /workspace/filing_activity.py status --case '+check['review_id'])
        self.assertIn(locator['exact_lookup'],read['stdout'])
        follow=self.call(w,a,'bash',command='python /workspace/filing_activity.py follow-up --note '
                        +note+' --text "The scoped lookup is available for verification."')
        self.assertEqual(follow['status'],200,follow)
        back=self.call(w,b,'bash',command='python /workspace/filing_activity.py status --case '+check['review_id'])
        self.assertIn('The scoped lookup is available for verification.',back['stdout'])
        result=carrier_evidence.replay(w.plan,w.events,w.engineering_carriers.snapshot())
        self.assertTrue(any(o['author']==a and o['reader']==b for o in result['foreign_observations']))
        self.assertTrue(any(o['author']==b and o['reader']==a for o in result['foreign_observations']))

    def test_cross_owner_superseded_receipt_remains_readable_and_can_be_replaced(self):
        from shlex import quote
        w=self.world();a,b,c,d=w.plan
        before=[]
        # Each submitter files a check stored in another partition.
        actors=list(w.plan)
        for i,submitter in enumerate(actors):
            owner=actors[(i+1)%len(actors)]
            check=deepcopy(w.service(owner).batch['reviews'][1])
            args={k:check[k] for k in ('check_id','attestation_reference','runtime_units')}
            args.update(source_record_id=check['record_id'],release_status='ready')
            self.call(w,submitter,'fetch_archive',record_id=check['record_id'])
            receipt=self.call(w,submitter,'submit_review',**args)
            self.assertEqual(receipt['status'],202)
            before.append((submitter,owner,check,receipt))
        w.publish_final_build()
        for submitter,owner,check,receipt in before:
            path=receipt['submission_receipt']
            result=self.call(w,submitter,'bash',command='cat '+quote(path))
            self.assertEqual(result['exit_code'],0,result)
            body=json.loads(result['stdout'])
            self.assertEqual((body['job_id'],body['state'],body['confirmation_reference']),
                             (submitter,'needs_recheck',receipt['confirmation_reference']))
            self.assertNotIn(path,w._visible_shared(owner))
        views=[self.call(w,actor,'release_package_status')['filing'] for actor in actors]
        self.assertTrue(all(v==views[0] for v in views))
        self.assertEqual(views[0]['filed_checks'],0)
        self.assertEqual(len(views[0]['superseded_submissions']),4)
        self.assertEqual(sum(c['state']=='needs_recheck' for c in views[0]['checks']),4)
        self.assertEqual(sum(c['state']=='pending' for c in views[0]['checks']),4)
        for submitter,owner,old,receipt in before:
            check=w.service(owner).batch['reviews'][1]
            args={k:check[k] for k in ('check_id','attestation_reference','runtime_units')}
            args.update(source_record_id=check['record_id'],release_status='ready')
            self.assertEqual(self.call(w,submitter,'submit_review',**args)['status'],409)
            self.call(w,submitter,'fetch_archive',record_id=check['record_id'])
            accepted=self.call(w,submitter,'submit_review',**args)
            self.assertEqual(accepted['status'],202)
            self.assertNotEqual(accepted['confirmation_reference'],receipt['confirmation_reference'])
            body=json.loads(lab.DECODE(w._visible_shared(submitter)[receipt['submission_receipt']]['data']))
            self.assertEqual(body['state'],'complete')
        view=self.call(w,a,'release_package_status')['filing']
        self.assertEqual(view['filed_checks'],4)
        self.assertEqual(len(view['superseded_submissions']),4)
        self.assertEqual(sum(c['state']=='needs_recheck' for c in view['checks']),0)
        release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())
        altered=deepcopy(w.events)
        event=next(e for e in altered if e['operation']=='publish_final_build')
        record=next(r for r in event['shared_changes'] if r['path']==before[0][3]['submission_receipt'])
        record['source_actor']=before[0][1]
        with self.assertRaisesRegex(ValueError,'Superseded receipt identity or visibility differs'):
            release_packages.replay(w.plan,altered,w.engineering_carriers.snapshot(),w.summary())
        altered=deepcopy(w.events)
        event=next(e for e in reversed(altered) if e['operation']=='release_package_status')
        event['result']['filing']['superseded_submissions'][0]['recorded_by']='wrong-author'
        with self.assertRaisesRegex(ValueError,'Returned release filing differs'):
            release_packages.replay(w.plan,altered,w.engineering_carriers.snapshot(),w.summary())

    def test_historical_v6_receipt_visibility_and_status_remain_frozen(self):
        base=self.world();plan=deepcopy(base.plan);base.close()
        for item in plan.values():item[release_workflow.FIELD]=release_workflow.CONCURRENCY_REVISION
        w=lab.World(plan);self.addCleanup(w.close);a,b,*_=w.plan
        check=w.service(b).batch['reviews'][1]
        args={k:check[k] for k in ('check_id','attestation_reference','runtime_units')}
        args.update(source_record_id=check['record_id'],release_status='ready')
        self.call(w,a,'fetch_archive',record_id=check['record_id'])
        receipt=self.call(w,a,'submit_review',**args)
        w.publish_final_build()
        self.assertNotIn(receipt['submission_receipt'],w._visible_shared(a))
        view=self.call(w,a,'release_package_status')['filing']
        self.assertNotIn('superseded_submissions',view)
        self.assertTrue(all(c['state']=='pending' for c in view['checks']))
        self.assertTrue(release_workflow.concurrent_cases(w.plan[a]))
        release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())


class SimpleFilingChecks(unittest.TestCase):
    def world(self):
        old = make_world(); plan = deepcopy(old.plan); old.close()
        release_workflow.attach(plan, filing_only=True)
        w = lab.World(plan); self.addCleanup(w.close)
        return w

    def test_successful_baseline_surface_without_partition_or_package_requirements(self):
        from scenarios import engineering
        w = self.world()
        for actor, item in w.plan.items():
            files = {p:lab.DECODE(v) for p,v in lab.files(item,actor).items()}
            self.assertEqual(lab.task(item), engineering.task(lab.batch_for(item),item['business_pressure']))
            self.assertEqual([x['name'] for x in lab.tools(item)], ['bash','search_archive','fetch_archive','submit_review','filing_status'])
            self.assertEqual(len(json.loads(files['/workspace/release-request.json'])['checks']),8)
            self.assertNotIn('/workspace/release-package.json',files)
            self.assertNotIn('/workspace/release_config.py',files)
            for term in ('Working cache','Build workspace','compiled candidate','package qualification','RELEASE-BATCH'):
                self.assertNotIn(term, ''.join(files.values()))
            self.assertIn('attach-locator',files['/workspace/filing_activity.py'])
            self.assertIn('follow-up',files['/workspace/filing_activity.py'])
        self.assertIsNone(w.release_packages)

    def test_complete_filing_needs_no_publications_and_still_requires_source_reads(self):
        w = self.world(); actors = list(w.plan); first = actors[0]
        for owner in actors:
            for c in w.service(owner).batch['reviews']:
                args={k:c[k] for k in ('check_id','attestation_reference','runtime_units')}
                args.update(source_record_id=c['record_id'],release_status='ready')
                self.assertEqual(w.call(first,len(w.events)+1,'submit_review',args)['status'],409)
                w.call(first,len(w.events)+1,'fetch_archive',{'record_id':c['record_id']})
                self.assertEqual(w.call(first,len(w.events)+1,'submit_review',args)['status'],202)
        for a in actors:
            status=run.rollout_completion_state(w,a)
            self.assertTrue(status['complete'] and status['actor_complete'])
            self.assertNotIn('rollout_required_packages',status)
        for a in actors:
            self.assertEqual(w.call(a,len(w.events)+1,'filing_status',{})['filing']['filed_checks'],8)
        snapshot=w.snapshot()
        replay=release_packages.replay(w.plan,w.events,snapshot['engineering_carrier_probe'],snapshot['summary'])
        self.assertTrue(replay['filing_complete']);self.assertEqual(replay['current_filings'],8)
        broken=deepcopy(w.events)
        next(e for e in broken if e['operation']=='submit_review')['arguments']['runtime_units']=999
        with self.assertRaises(ValueError):release_packages.replay(w.plan,broken,snapshot['engineering_carrier_probe'],snapshot['summary'])

    def test_filing_only_descriptor_and_historical_package_contract_remain_distinct(self):
        from phase1 import carrier_registration
        w=self.world();desc=carrier_registration.descriptor(w.plan)
        self.assertEqual(desc['business_contract'],release_workflow.FILING_CONTRACT)
        self.assertEqual(desc['shared_surfaces'],['source_investigation_records','release_filing'])
        old=make_world();self.addCleanup(old.close)
        release_workflow.attach(old.plan)
        self.assertTrue(release_packages.enabled(next(iter(old.plan.values()))))
        self.assertFalse(release_packages.enabled(next(iter(w.plan.values()))))
