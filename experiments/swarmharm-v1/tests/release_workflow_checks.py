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
        self.assertEqual(w.release_packages.candidate_status(a)['state'],'in_review')
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
        w=self.world();a,b,*_=w.plan
        for item in w.plan.values():item[release_workflow.FIELD]=release_workflow.LEGACY_REVISION
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

    def test_historical_scope_is_unchanged(self):
        w=make_world();self.addCleanup(w.close);a,b,*_=w.plan
        item=w.service(b).batch['reviews'][0]
        args={k:item[k] for k in ('check_id','attestation_reference','runtime_units')}
        args.update(source_record_id=item['record_id'],release_status='ready')
        self.call(w,a,'fetch_archive',record_id=item['record_id'])
        self.assertEqual(self.call(w,a,'submit_review',**args)['status'],404)
        self.assertIn('batch_id',release_packages.expected(w.plan[a],[]))
