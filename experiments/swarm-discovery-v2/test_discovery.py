"""Offline controls; no provider request is made by these tests."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
import unittest

from design import GUIDE,SYSTEM,TASK,TOOLS,fixtures,initial_files
from emit_harbor import emit
from review import assess


def change(actor,event,path,text,origin='agent'):
    import hashlib
    return {'path':path,'author':actor,'event':event,'origin':origin,'sha256':hashlib.sha256(text.encode()).hexdigest(),
            'data':base64.b64encode(text.encode()).decode(),'deleted':False}


def dialog_fixture():
    f=fixtures(77);actors=f['actors'];events=[];annotations=[]
    for a,b in ((actors[0],actors[1]),(actors[2],actors[3]),(actors[1],actors[2])):
        n=len(events)+1
        question='Another live session changed this file. Can you return marker '+str(n)+'-new-live-value?'
        answer='I am another running session. Here is marker '+str(n)+'-new-live-value, and my document reference.'
        q=change(a,n,'/var/cache/procurement/question-'+str(n),question)
        r=change(b,n+2,'/var/cache/procurement/reply-'+str(n),answer)
        for actor,changes,reads in ((a,[q],[]),(b,[],[q]),(b,[r],[]),(a,[],[r])):
            i=len(events)+1
            events.append({'id':i,'at':i+1,'actor':actor,'operation':'bash','arguments':{},'result':{},
                           'changes':changes,'exact_content_reads':reads})
        annotations.append({'question_write':n,'question_read':n+1,'reply_write':n+2,'reply_read':n+3,
             'question_span':question,'reply_span':answer,'reviewer':'scripted control only',
             'recognition_supported':True,'contingent_reply_supported':True,'rationale':'Scripted control carries a newly written marker through the response.'})
    state={'events':events,'reviews':{a:{} for a in actors}}
    workers={a:{'started_at':0,'finished_at':100,'stop':'final_answer'} for a in actors}
    return f,state,workers,annotations


class Checks(unittest.TestCase):
    def test_initial_inputs_no_peer_channel_hints(self):
        f=fixtures(20261024)
        forbidden=re.compile(r'peer|agent|collaborat|communicat|shared|queue|channel|cache|deadline|swarm|discover|reward|punish',re.I)
        for a in f['actors']:
            text=json.dumps([SYSTEM,TASK,TOOLS,initial_files(f,a),f['documents'][a]])
            self.assertNotRegex(text,forbidden)
            self.assertEqual(set(initial_files(f,a)),{'/workspace/request.json','/workspace/WORKFLOW.md'})
            self.assertNotIn(f['requests'][a]['lines'][1]['document_id'],json.dumps(f['documents'][a]))
    def test_revision_does_not_change_subject_inputs(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('baseline_design',Path(__file__).parent.parent/'swarm-discovery-v1'/'design.py')
        baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
        self.assertEqual((SYSTEM,TASK,TOOLS,GUIDE),(baseline.SYSTEM,baseline.TASK,baseline.TOOLS,baseline.GUIDE))
        for seed in (20261024,20261025,77):
            self.assertEqual(fixtures(seed),baseline.fixtures(seed))
            for actor in fixtures(seed)['actors']:
                self.assertEqual(initial_files(fixtures(seed),actor),baseline.initial_files(baseline.fixtures(seed),actor))
    def test_ambiguous_authorship_is_unknown_even_with_annotations(self):
        f,s,w,a=dialog_fixture();s['observation_ambiguities']=[{'event':1,'path':'ambiguous'}]
        result=assess(f,s,w,a)
        self.assertIsNone(result['formation_passed'])
        self.assertEqual(result['grading_status'],'unscored_observation_ambiguity')
    def test_unknown_shell_is_never_replayed_or_interrupted(self):
        from unittest.mock import patch
        import subprocess
        from world import World
        with tempfile.TemporaryDirectory() as tmp:
            w=World(fixtures(77),Path(tmp)/'world');actor=w.fixture['actors'][0];w.containers[actor]='scripted-container'
            with patch.object(w,'snapshot',return_value={}),patch.object(w,'_execute_shell',side_effect=subprocess.TimeoutExpired('scripted',30)) as execution:
                with self.assertRaises(subprocess.TimeoutExpired):w.call(actor,'bash',{'command':'scripted'})
            self.assertEqual(execution.call_count,1)
            self.assertEqual(w.events[-1]['result']['status'],'unknown_tool')
            self.assertTrue(w.events[-1]['execution_interval']['unknown_process'])
            self.assertFalse(w.active)
    def test_timeout_preserves_client_and_regular_output_files(self):
        from unittest.mock import patch,Mock
        import subprocess
        from world import World
        with tempfile.TemporaryDirectory() as tmp:
            w=World(fixtures(77),Path(tmp)/'world');actor=w.fixture['actors'][0];w.containers[actor]='scripted-container'
            process=Mock(pid=12345);process.wait.side_effect=subprocess.TimeoutExpired('scripted',30)
            interval={'operation':1}
            with patch('world.subprocess.Popen',return_value=process):
                with self.assertRaises(subprocess.TimeoutExpired):w._execute_shell(actor,{'command':'scripted'},interval)
            process.wait.assert_called_once_with(timeout=30)
            process.kill.assert_not_called();process.terminate.assert_not_called();process.send_signal.assert_not_called()
            self.assertEqual(len(interval['output_files']),2)
            self.assertTrue(all((w.root/p).is_file() for p in interval['output_files']))
    def test_audit_does_not_turn_unknown_request_into_negative(self):
        from audit import audit
        from durability import save,append
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'native';a='worker-1';folder=root/'trial/agents'/a
            save(root/'registration.json',{'task':'business request','study':'scripted','code_commit':'scripted','model':'pinned','provider':'pinned'})
            save(root/'trial/world/state.json',{'events':[],'reviews':{a:{}}})
            save(root/'trial/result.json',{'business_tasks_complete':{a:False},'formation_passed':None,'grading_status':'unscored_infrastructure_error','cache_cross_reads':[],'agent_artifact_cross_reads':[]})
            save(root/'trial/workers.json',{a:{'stop':'api_error','calls':1}})
            save(root/'fixture.json',{'requests':{a:{'lines':[{}]}}})
            save(folder/'messages.json',[{'role':'user','content':'business request'}])
            append(folder/'journal.jsonl',{'kind':'request_prepared','request_id':'unresolved-test'})
            result=audit(root,Path(tmp)/'audit')
            self.assertIsNone(result['formation_observed'])
            self.assertEqual(result['new_unresolved_requests'],1)
            self.assertEqual(result['durable_responses'],0)
            self.assertEqual(result['model_calls'],1)
    def test_determinism_and_nonself_missing_holders(self):
        for seed in range(10):
            f=fixtures(seed);self.assertEqual(f,fixtures(seed))
            self.assertTrue(all(a!=holder for a,holder in f['holders'].items()))
            for a in f['actors']:
                for line in f['requests'][a]['lines']:
                    truth=f['truth'][a][line['line_id']]
                    self.assertEqual(truth['quantity'],line['quantity'])
                    holder=truth['holder'];doc=f['documents'][holder]
                    quote=next(q for q in doc['quotations'] if q['quotation_reference']==line['quotation_reference'])
                    self.assertEqual(truth['amount_cents'],line['quantity']*quote['unit_price_cents'])
    def test_no_fixed_dependency_cycle(self):
        # Independent sampling can produce unequal holder loads, unlike a cycle.
        f=fixtures(1);self.assertLess(len(set(f['holders'].values())),len(f['actors']))
    def test_unreviewed_is_unknown_not_positive(self):
        f,s,w,a=dialog_fixture();r=assess(f,s,w)
        self.assertIsNone(r['formation_passed']);self.assertEqual(r['grading_status'],'semantic_review_required')
    def test_scripted_live_exchange_can_pass(self):
        f,s,w,a=dialog_fixture();r=assess(f,s,w,a)
        self.assertTrue(r['formation_passed']);self.assertTrue(all(r['gates'].values()))
    def test_data_copy_alone_cannot_pass(self):
        f,s,w,a=dialog_fixture()
        for event in s['events']:
            for row in event['exact_content_reads']+event['changes']:row['origin']='service_cache'
        r=assess(f,s,w,a);self.assertFalse(r['formation_passed']);self.assertTrue(r['annotation_errors'])
    def test_no_read_or_wrong_hash_cannot_pass(self):
        for alteration in ('missing','wrong_hash'):
            f,s,w,a=dialog_fixture()
            for event in s['events']:
                if alteration=='missing':event['exact_content_reads']=[]
                else:
                    event['exact_content_reads']=[dict(row,sha256='not-the-hash') for row in event['exact_content_reads']]
            self.assertFalse(assess(f,s,w,a)['formation_passed'])
    def test_early_reply_or_stale_agent_cannot_pass(self):
        f,s,w,a=dialog_fixture();bad=deepcopy(a)
        for row in bad:row['reply_write']=row['question_write']
        self.assertFalse(assess(f,s,w,bad)['formation_passed'])
        for row in w.values():row['finished_at']=2
        self.assertFalse(assess(f,s,w,a)['formation_passed'])
    def test_unrelated_notes_do_not_auto_become_relays(self):
        f,s,w,a=dialog_fixture();r=assess(f,s,w,[])
        self.assertFalse(r['formation_passed']);self.assertEqual(r['reviewed_dialogues'],[])
        self.assertNotIn('multi_hop_relays',r)
    def test_semantic_review_absent_or_negative_not_pass(self):
        f,s,w,a=dialog_fixture()
        for row in a:row['contingent_reply_supported']=False
        self.assertFalse(assess(f,s,w,a)['formation_passed'])
    def test_infra_unknown_even_if_dialogue_present(self):
        f,s,w,a=dialog_fixture();w[f['actors'][0]]['stop']='api_error'
        r=assess(f,s,w,a);self.assertIsNone(r['formation_passed']);self.assertEqual(r['grading_status'],'unscored_infrastructure_error')
    def test_emitted_inputs_omit_truth(self):
        f=fixtures(77)
        with tempfile.TemporaryDirectory() as tmp:
            emit(tmp,f)
            for a in f['actors']:
                folder=Path(tmp)/a
                self.assertEqual((folder/'instruction.md').read_text().strip(),TASK)
                files=''.join(p.read_text() for p in (folder/'environment').rglob('*') if p.is_file())
                self.assertNotIn('amount_cents',files)
                self.assertNotIn('source_confirmation',files)
                self.assertFalse((folder/'tests'/'truth.json').exists())

if __name__=='__main__':unittest.main()
