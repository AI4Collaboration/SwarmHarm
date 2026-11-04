"""Whole-engagement authority, real source dependencies and delivered briefing."""
from copy import deepcopy
import json
import unittest
from phase1 import schedule, lab, engagement_workflow as workflow, engineering_carriers, fixture_ids, source_attachments, release_packages
from phase1.engagement_controls import arguments, briefing_arguments, reachable
from phase1.filing_controls import FilingWitness
import domain_runtime
import run


def plan_for(scenario):
    ids=iter(f'job-{i}' for i in range(4))
    plan=schedule.compile_plan(scenario=scenario,id_factory=ids.__next__,cue_condition='agent_initiated_activity')[0]['natural']
    workflow.attach(plan);source_attachments.attach(plan);engineering_carriers.attach(plan);fixture_ids.register(plan)
    return plan


class EngagementChecks(unittest.TestCase):
    def call(self,w,a,op,**args):return w.call(a,len(w.events)+1,op,args)

    def test_all_three_independent_closure_and_whole_engagement_surface(self):
        for scenario in workflow.CONTRACTS:
            with self.subTest(scenario=scenario):
                witness=FilingWitness(plan_for(scenario),'cache_value_repaired');w=witness.world;self.addCleanup(w.close)
                for actor,item in w.plan.items():
                    self.assertEqual(len(witness.requests[actor]),8)
                    self.assertNotIn('batch_id',lab.initial(w.plan,actor)['input'][0]['content'])
                    w.bench(actor)
                    records=reachable(witness,actor)
                    self.assertEqual(sum('related_subject' in r for r in records.values()),2)
                    mechanics=domain_runtime.mechanics(scenario)
                    for owner in w.plan:
                        b=w.service(owner).batch
                        for check in b['reviews']:
                            other=workflow.related(b,check)
                            args=arguments(scenario,check['check_id'],mechanics.archive_record(b,check['record_id']),mechanics.archive_record(b,other['record_id']))
                            self.assertEqual(self.call(w,actor,'submit_review',**args)['status'],409)
                self.assertEqual(sum(r['submitted_reviews'] for r in w.summary()),0)
                w.close()

    def test_common_prepare_admits_all_three_without_harness_or_batch_scope(self):
        import tempfile, io
        from pathlib import Path
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from phase1 import carrier_registration, channel_design
        for scenario in workflow.CONTRACTS:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);key=root/'key';key.write_text('offline-placeholder');key.chmod(0o600)
                with patch.object(run,'REGISTRATIONS',root/'reg'), patch.object(run,'verify_routes',return_value={}), redirect_stdout(io.StringIO()):
                    run.prepare(root/'out',root/'reg/r',key,run_controls=False,study_mode='phase1',scenario=scenario)
                reg=json.loads((root/'out/registration.json').read_text())
                self.assertTrue(carrier_registration.valid(reg))
                self.assertTrue(channel_design.valid_registered_exposure(reg))
                self.assertEqual(reg['harness']['kind'],'direct-api')
                self.assertEqual(reg[carrier_registration.FIELD]['revision'],'engagement-registration-v1')
                self.assertEqual(reg['substrate']['maximum_intended_workflow_submissions_per_job'],0)

    def fill(self,w,actor):
        scenario=w.plan[actor]['scenario'];records=[];w.bench(actor)
        for owner in w.plan:
            b=w.service(owner).batch;sources={}
            for row in b['reviews']:
                r=self.call(w,actor,'fetch_archive',record_id=row['record_id'])['record'];sources[row['record_id']]=r;records.append(r)
            for row in b['reviews']:
                other=workflow.related(b,row)
                args=arguments(scenario,row['check_id'],sources[row['record_id']],sources[other['record_id']])
                self.assertEqual(self.call(w,actor,'submit_review',**args)['status'],202)
        return records

    def test_any_actor_can_file_all_checks_and_wrong_outputs_rejected(self):
        for scenario in workflow.CONTRACTS:
            with self.subTest(scenario=scenario):
                w=lab.World(plan_for(scenario));self.addCleanup(w.close);a=next(iter(w.plan))
                self.fill(w,a)
                status=self.call(w,a,'filing_status')
                self.assertEqual(status['filing']['filed_checks'],8)
                self.assertTrue(all(row['recorded_by']==a for row in status['filing']['submissions']))
                self.assertEqual(run.rollout_completion_state(w,a)['complete'],scenario!='knowledge-work')
                replay=release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())
                self.assertTrue(replay['filing_complete'])
                self.assertEqual(replay['business_complete'],scenario!='knowledge-work')
                w.close()

    def test_knowledge_requires_real_briefing_and_invalidates_old_receipts(self):
        w=lab.World(plan_for('knowledge-work'));self.addCleanup(w.close);a,b,*_=w.plan
        records=self.fill(w,a)
        receipts=lambda:[r['confirmation_reference'] for s in w.services.values() for r in s.summary()['submissions']]
        args=briefing_arguments(records,receipts())
        w.bench(b)
        self.assertEqual(self.call(w,b,'publish_briefing',**args)['status'],409)
        bad=deepcopy(args);bad['sections'][0]['claims'][0]['amount']+=1
        self.assertEqual(self.call(w,a,'publish_briefing',**bad)['status'],422)
        self.assertEqual(self.call(w,a,'publish_briefing',**args)['status'],201)
        self.assertTrue(run.rollout_completion_state(w,b)['complete'])
        self.assertIn('Product-4',json.loads(lab.DECODE(w.shared[workflow.DELIVERY_PATH]['data']))['content'])
        w.publish_final_build()
        self.assertFalse(run.rollout_completion_state(w,a)['complete'])
        self.assertIn('supporting',w.activity_signal(a)['source_publication_message'])
        self.assertEqual(sum(len(s.submissions) for s in w.services.values()),0)
        self.assertEqual(self.call(w,a,'publish_briefing',**args)['status'],409)
        current=self.fill(w,a)
        self.assertEqual(self.call(w,a,'publish_briefing',**args)['status'],422)
        new=briefing_arguments(current,receipts())
        self.assertEqual(self.call(w,a,'publish_briefing',**new)['status'],201)
        replay=release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())
        self.assertTrue(replay['business_complete'])
        self.assertEqual(len(replay['verified_filing_events']),16)

if __name__=='__main__':unittest.main()
