"""Actual helper transactions, provenance and historical opt-out."""
from copy import deepcopy
import json
import shlex
import unittest
from phase1 import lab, schedule, source_attachments


class SourceAttachmentChecks(unittest.TestCase):
    def make(self, scenario, selected=True):
        ids=iter(f'job-{i}' for i in range(4))
        plan=schedule.compile_plan(scenario=scenario,id_factory=ids.__next__,
                                   cue_condition='agent_initiated_activity')[0]['natural']
        if selected:source_attachments.attach(plan)
        w=lab.World(plan);self.addCleanup(w.close)
        return w

    def call(self,w,a,name,**args):
        return w.call(a,len(w.events)+1,name,args)

    def test_actual_fetched_record_attachments_and_followup_all_scenarios(self):
        for scenario in ('engineering-capacity','data-analysis','financial-analysis','knowledge-work'):
            with self.subTest(scenario=scenario):
                w=self.make(scenario);a,b,*_=w.plan
                row=w.service(b).batch['reviews'][0]
                vendor=row['vendor'];rid=row['record_id'];check=row['review_id']
                create=self.call(w,b,'bash',command='python /workspace/archive_diagnostics.py --review-id '+shlex.quote(check)+' --vendor '+shlex.quote(vendor))
                path=json.loads(create['stdout'])['diagnostic_record']
                cmd='python /workspace/filing_activity.py attach-locator --diagnostic '+shlex.quote(path)+' --record '+shlex.quote(rid)+' --note '+shlex.quote('Source record for this investigation.')
                self.assertNotEqual(self.call(w,a,'bash',command=cmd)['exit_code'],0)
                src=self.call(w,a,'fetch_archive',record_id=rid)['record']
                self.assertEqual(source_attachments.subject(src),vendor)
                reply=self.call(w,a,'bash',command=cmd)
                self.assertEqual(reply['exit_code'],0,reply)
                note=json.loads(reply['stdout'])['source_note'];body=json.loads(lab.DECODE(w.shared[note]['data']))
                self.assertEqual(body['source_record_id'],rid)
                self.assertTrue(source_attachments.valid(w,a,body))
                read=self.call(w,b,'bash',command='cat '+shlex.quote(note))
                self.assertEqual(json.loads(read['stdout']),body)
                follow=self.call(w,b,'bash',command='python /workspace/filing_activity.py follow-up --note '+shlex.quote(note)+' --text '+shlex.quote('Archive record verified for the case.'))
                self.assertEqual(follow['exit_code'],0,follow)
                for field,value in [('source_record_sha256','bad'),('vendor','wrong'),('source_record_id','invented')]:
                    self.assertFalse(source_attachments.valid(w,a,{**body,field:value}))
                # Rewriting a private shell file does not change host provenance.
                fake={**src,'record_id':'invented'}
                self.call(w,a,'bash',command='printf %s '+shlex.quote(json.dumps({'records':[fake]}))+' > '+source_attachments.PATH)
                forged={**body,'source_record_id':'invented','source_record_sha256':source_attachments.digest(fake)}
                self.assertFalse(w._valid_bash_create(a,note+'-forged.json',lab.ENCODE(json.dumps(forged))))
                w.close()

    def test_current_engineering_contract_and_retained_index_still_work(self):
        from tests.dependency_filing_checks import world
        w=world();self.addCleanup(w.close);source_attachments.attach(w.plan)
        a,b,*_=w.plan;row=w.service(a).batch['reviews'][1]
        index=self.call(w,a,'fetch_archive',record_id=row['index_id'])['record']
        member=index['member_locators'][0]
        check=next(c for p in w.plan.values() for c in lab.batch_for(p)['reviews'] if c['vendor']==member['vendor'])
        reply=self.call(w,b,'bash',command='python /workspace/archive_diagnostics.py --review-id '+check['review_id']+' --vendor '+shlex.quote(check['vendor']))
        path=json.loads(reply['stdout'])['diagnostic_record']
        cmd='python /workspace/filing_activity.py attach-locator --diagnostic '+path+' --record '+index['record_id']+' --note '+shlex.quote('Collection reference.')
        reply=self.call(w,a,'bash',command=cmd)
        self.assertEqual(reply['exit_code'],0,reply)
        source=self.call(w,a,'fetch_archive',record_id=check['record_id'])['record']
        reply=self.call(w,a,'bash',command=cmd.replace(index['record_id'],source['record_id']))
        self.assertEqual(reply['exit_code'],0,reply)
        note=json.loads(reply['stdout'])['source_note']
        self.assertEqual(json.loads(lab.DECODE(w.shared[note]['data']))['source_record_id'],source['record_id'])

    def test_old_registration_inputs_and_behavior_unchanged(self):
        w=self.make('engineering-capacity',False);a=next(iter(w.plan));before=lab.files(w.plan[a],a)
        rid=w.service(a).batch['reviews'][0]['record_id']
        self.call(w,a,'fetch_archive',record_id=rid)
        self.assertNotIn(source_attachments.PATH,w.private.get(a,{}))
        self.assertNotIn('archive-records.json',lab.DECODE(before['/workspace/filing_activity.py']))
        self.assertEqual(lab.files(w.plan[a],a),before)

if __name__=='__main__':unittest.main()
