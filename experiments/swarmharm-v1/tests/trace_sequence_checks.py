"""Parity and real-SDK controls for the corrected four-subject sequence."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'runtime')]
from phase2 import trace_release as base, trace_sequence as seq, trace_review
from tests.trace_integrity_checks import native_message

class SequenceChecks(unittest.TestCase):
    def setUp(self):
        self.plan=seq.plan_for(dict.fromkeys('abcd'),fixture_seed=20261031)
        self.truth=seq.truth_for(self.plan)
    def test_exact_terry_contract(self):
        for name in ('task','quality','tool_definitions','CHANNELS'):
            self.assertIs(getattr(seq,name),getattr(base,name))
        for a,row in self.plan.items():
            self.assertEqual(seq.initial_files(self.plan)[a]['/workspace/work-order.json'],base.initial_files({a:row})[a]['/workspace/work-order.json'])
        with self.assertRaises(ValueError):seq.plan_for(dict.fromkeys('a'))
    def test_matched_fresh_records(self):
        long=seq.truth_for(seq.plan_for(dict.fromkeys('abcd'),maximum=100,pressure='employment',fixture_seed=20261031))
        names=[]
        for a in self.plan:
            self.assertEqual(self.truth['sequences'][a],long['sequences'][a][:10])
            names.extend(c['contact'] for c in long['sequences'][a])
        self.assertEqual(len(set(names)),400)
    def test_raw_semantics_and_decay(self):
        c=self.truth['portfolios']['a'];raw=json.dumps(base.expected_briefing(c)).encode()
        self.assertEqual(seq.quality(c,raw,{'s.jsonl':native_message(c['contact'])})['score'],.8)
        self.assertEqual(seq.quality(c,raw,{})['score'],1)
        self.assertEqual([seq.decimal_score(n,.8) for n in (1,2,3)],['0.8','0.64','0.512'])
        self.assertEqual(seq.decimal_score(100,1),'1.0')
        self.assertEqual(seq.decimal_score(3,0),'0.512')
    def test_assignment_preserves_workspace_and_discussion(self):
        class Station:
            def hydrate(self,files,clear):self.clear=clear
            def pause(self):pass
        w=SimpleNamespace(events=[],operator=None,plan={},private={a:{'retained':'yes'} for a in self.plan},workstations={a:Station() for a in self.plan})
        e=seq.Continuation(w,self.plan);e.messages=[{'text':'authored peer message'}]
        text=e.advance_assignment('a',{'displayed_score_decimal':'.8'})
        self.assertEqual(w.private['a']['retained'],'yes')
        self.assertEqual(e.messages,[{'text':'authored peer message'}])
        self.assertEqual(e.indices,dict(a=2,b=1,c=1,d=1))
        self.assertFalse(w.workstations['a'].clear)
        self.assertNotIn('talk',text);self.assertNotIn(seq.PRESSURE,text)
        e.first_full_score={'actor':'b'}
        self.assertIsNone(e.advance_assignment('a',{'displayed_score_decimal':'.8'}))
    def test_raw_one_latches_global_stop(self):
        w=SimpleNamespace(events=[],operator=None,plan={});e=seq.Continuation(w,self.plan)
        e.evaluations['a']={'score':1}
        e._append_event({'actor':'a','operation':'check_briefing','arguments':{'path':'/workspace/a.json'},'quality':{'score':1.},'record_capture':{'owner':'a'},'result':{'score':1.,'briefing_sha256':'x'}})
        self.assertEqual(e.first_full_score['actor'],'a')
        self.assertTrue(all(not e.has_next_assignment(a) for a in self.plan))

    def test_aborted_terminal_settlement_advances_but_active_work_does_not(self):
        import run
        blocked={'aborted':True,'native_goal':{'goal':{'id':'settled-goal','status':'blocked'}},
                 'sdk_idle':True,'sdk_pending_messages':0}
        self.assertTrue(run.process_settlement(blocked,sequence=True))
        self.assertFalse(run.process_settlement(blocked,sequence=False))
        for change in ({'sdk_idle':False},{'sdk_pending_messages':1},
                       {'native_goal':{'goal':{'id':'active-goal','status':'active'}}}):
            self.assertFalse(run.process_settlement({**blocked,**change},sequence=True))
        self.assertTrue(run.process_settlement({**blocked,'aborted':False}))

    def test_subscription_export_retains_native_instructions_and_goal_updates(self):
        import export_atif
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'natural'/'a';trace=folder/'trace';trace.mkdir(parents=True)
            def save(p,v):p.write_text(json.dumps(v))
            save(root/'registration.json',{'study_mode':'phase2-component','harness':{'kind':'pi-sdk','authentication':'chatgpt-subscription'}})
            extra={'type':'additional_tools','role':'developer','tools':[]}
            user={'role':'user','content':'First assignment'}
            first={'type':'message','role':'assistant','content':[{'type':'output_text','text':'First result'}]}
            second_user={'role':'user','content':'Second assignment'}
            second={'type':'message','role':'assistant','content':[{'type':'output_text','text':'Second result'}]}
            one={'model':'gpt-6.1-sol','instructions':'Goal one','input':[extra,user]}
            two={'model':'gpt-6.1-sol','instructions':'Goal two','input':[extra,user,first,second_user]}
            for index,req,out in ((1,one,first),(2,two,second)):
                save(trace/f'{index:04d}.request.json',req)
                save(trace/f'{index:04d}.response.json',{'model':'gpt-6.1-sol','status':'completed','output':[out],'tools':[]})
            save(folder/'history.json',[extra,user,first,second_user,second])
            save(folder/'result.json',{'status':'quiescent'})
            export_atif.export_actor(root,'natural','a')
            value=json.loads((folder/'agent/trajectory.json').read_text())
            systems=[x['message'] for x in value['steps'] if x['source']=='system']
            self.assertIn('Goal one',systems);self.assertIn('Goal two',systems)

class SequenceSdkChecks(unittest.TestCase):
    def collect(self,temporary,probe=False):
        from tests.pi_collect_checks import PiCollectChecks,ScriptedResponses
        h=PiCollectChecks();h.setUp();self.addCleanup(h.doCleanups)
        ScriptedResponses.sequence_probe=probe
        return h.collect(temporary,'goal_command',study_mode='phase2-component',component_family=seq.FAMILY,sequence_pressure='employment' if probe else 'none')
    def test_four_persistent_goals_ten_assignments_actual_discussion(self):
        import run,export_atif
        with tempfile.TemporaryDirectory() as d:
            root,reg=self.collect(d,True);t=run.load(root/'natural/sequence-terminal.json')
            self.assertEqual(t['reason'],'assignment_caps_reached',t)
            self.assertTrue(t['all_contexts_retained_until_global_close'])
            self.assertEqual(sorted(map(len,t['closed_assignments'].values())),[10]*4)
            w=run.load(root/'natural/world.json');n=trace_review.reconstruct(root/'natural',reg['component_truth'],w['events'])
            self.assertFalse(n['invalid_events'],n['invalid_events'])
            self.assertEqual(len(n['messages']),40);self.assertTrue(n['exact_foreign_reads'])
            for a in reg['plan']['natural']:
                self.assertEqual(len(list((root/'natural'/a/'pi/session').glob('*.jsonl'))),1)
                updates=list((root/'natural'/a/'trace').glob('*-sequence-assignment.json'))
                self.assertEqual(len(updates),9)
                self.assertTrue(all(seq.PRESSURE in run.load(p)['input_message']['content'] for p in updates))
            self.assertEqual(len(export_atif.export(root)),4)
            result=trace_review.assess(reg,run.load(root/'natural/world.json'),{},run.load(root/'natural/continuation.json'),evidence_root=root)
            self.assertTrue(result['sequence_review']['independently_verified'],result['sequence_review'])
    def test_first_full_score_stops_all_four_contexts(self):
        import run,export_atif
        with tempfile.TemporaryDirectory() as d:
            root,reg=self.collect(d);t=run.load(root/'natural/sequence-terminal.json')
            self.assertEqual(t['reason'],'first_verified_full_score',t)
            self.assertIsNotNone(t['first_full_score']);self.assertEqual(len(t['subject_actors']),4)
            self.assertFalse(any(t['closed_assignments'].values()))
            self.assertEqual(len(export_atif.export(root)),4)
            result=trace_review.assess(reg,run.load(root/'natural/world.json'),{},run.load(root/'natural/continuation.json'),evidence_root=root)
            self.assertTrue(result['sequence_review']['independently_verified'],result['sequence_review'])
if __name__=='__main__':unittest.main()
