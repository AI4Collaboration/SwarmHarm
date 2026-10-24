import hashlib,json
from pathlib import Path
import subprocess,tempfile,unittest
from unittest.mock import Mock,patch
from check_inputs import check
from design import make_plan,files,initial,lab,review,TOOLS
from status import assess,feedback
from safe_runtime import Workstation,UnknownExecution

class Checks(unittest.TestCase):
    def test_assembled_inputs_no_peer_or_channel_hints(self):self.assertEqual(check()['status'],'passed')
    def test_pinned_business_source_unchanged(self):
        root=Path(__file__).parent;manifest=json.loads((root/'UPSTREAM.json').read_text())
        for name,digest in manifest['unchanged_files'].items():self.assertEqual(hashlib.sha256((root/'vendor'/name).read_bytes()).hexdigest(),digest)
    def test_client_is_upstream_client_without_seeded_notes(self):
        plan,_=make_plan();values=files(plan)
        for actor,item in plan.items():
            expected=lab.filing_activity_helper(actor,lab.batch_for(item),item['business_pressure']['contract_reference'])
            self.assertEqual(lab.DECODE(values[actor]['/workspace/filing_activity.py']),expected)
            self.assertEqual(len(values[actor]),5)
            self.assertTrue(all(p.startswith('/workspace/') for p in values[actor]))
    def test_task_does_not_expose_gold_or_local_solution(self):
        plan,_=make_plan();values=files(plan)
        for actor,item in plan.items():
            text=''.join(lab.DECODE(v) for v in values[actor].values())
            for case in lab.batch_for(item)['reviews']:
                self.assertNotIn(case['quote_reference'],text);self.assertNotIn(case['record_id'],text)
            self.assertNotIn('collection:supplier-holdings-',text)
        self.assertTrue(all(review.intended_workflow_impossible(plan).values()))
    def test_tool_arguments_match_upstream(self):
        self.assertEqual([(t['function']['name'],t['function']['parameters']) for t in TOOLS],[(t['name'],t['parameters']) for t in lab.tools()])
    def test_feedback_is_counts_without_client_or_continuation_coaching(self):
        text=feedback({'complete':False,'filed':1,'assigned':2,'outstanding':['R'],'filing_filed':4,'filing_assigned':8,'pending_confirmations':0})
        self.assertIn('4/8',text)
        for word in ('continue','filing_activity','peer','channel','agent','communicat','search'):self.assertNotIn(word,text.lower())
    def test_empty_or_unrelated_work_does_not_prove_exchange(self):
        plan,_=make_plan();state={'events':[],'summary':[{'submitted_reviews':0,'assigned_reviews':2} for a in plan]}
        workers={a:{'started_at':1,'finished_at':2,'stop':'wall_clock'} for a in plan}
        result=assess(plan,state,workers);self.assertFalse(result['functional_communication_passed']);self.assertFalse(result['grounded_request_reply_use_chains'])
        workers[next(iter(plan))]['stop']='api_error';self.assertIsNone(assess(plan,state,workers)['functional_communication_passed'])
    def test_unknown_execution_never_kills_or_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=object.__new__(Workstation);w.root=Path(tmp);w.name='scripted-container';w.invocations=0
            process=Mock(pid=123);process.wait.side_effect=subprocess.TimeoutExpired('scripted',30)
            with patch('safe_runtime.subprocess.Popen',return_value=process) as spawn:
                with self.assertRaises(UnknownExecution):w._run(['scripted'])
            self.assertEqual(spawn.call_count,1);process.kill.assert_not_called();process.terminate.assert_not_called();process.send_signal.assert_not_called()
            self.assertTrue((w.root/'1/unknown.json').exists())
    def test_live_background_writer_holds_before_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=object.__new__(Workstation);w.root=Path(tmp);w.name='scripted-container'
            observation={'/workspace':{},'/registry':{},'/tmp':{},'background_processes':[{'pid':8,'comm':'scripted'}]}
            with patch.object(w,'_run',return_value=Mock(stdout=json.dumps(observation))) as run:
                with self.assertRaises(UnknownExecution):w.hydrate({},True)
            self.assertEqual(run.call_count,1)
    def test_lifecycle_methods_have_no_process_actions(self):
        w=object.__new__(Workstation);w.name='retained'
        with patch('safe_runtime.subprocess.Popen') as process:
            w.pause();w.resume();self.assertTrue(w.close()['retained']);process.assert_not_called()
    def test_harbor_inputs_and_frozen_workspaces_validate(self):
        from run import packages
        plan,_=make_plan();values=files(plan)
        with tempfile.TemporaryDirectory() as tmp:
            packages(Path(tmp),plan,values)
            for a in plan:
                p=Path(tmp)/a
                self.assertEqual((p/'instruction.md').read_text().strip(),initial(plan,a)[-1]['content'])
                for name,encoded in values[a].items():self.assertEqual((p/'environment'/name.lstrip('/')).read_text(),lab.DECODE(encoded))

if __name__=='__main__':unittest.main()
