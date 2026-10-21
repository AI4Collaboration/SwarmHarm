"""Scripted end-to-end controls; real contained files and zero model calls."""
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import checks
import run

class CollectorChecks(unittest.TestCase):
    def test_actual_request_share_use_and_public_copy(self):self.control(False,False)
    def test_incomplete_response_does_not_dispatch_client_delivery(self):self.control(True,False)
    def test_same_response_read_delivery_is_not_prior_body_adoption(self):self.control(False,True)
    def control(self,held,same_response):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'study';tiny={'calibration_sol56':checks.plan(True,True),'natural':checks.plan(False,True)}
            with patch.object(run,'make_plan',return_value=tiny),redirect_stdout(io.StringIO()):run.prepare(root)
            reg=run.load(root/'registration.json');c=checks.FIXTURES['projects'][0]
            def fake(body,directory,label,timeout=900):
                directory=Path(directory);step=int(label);operation=None;args=None;actor=directory.parent.name
                if directory.parent.name=='preflight':
                    if step==1:operation='confirm_service';args={}
                elif directory.parent.parent.name=='calibration_sol56':
                    if step in (1,2):operation='read_document';args={'name':c['batch_name'] if step==1 else c['terms_name']}
                    elif step==3:operation='submit_report';args={'json_text':json.dumps(run.lab.expected(checks.FIXTURES,tiny['calibration_sol56'][actor]))}
                else:
                    def source(name):
                        return next(json.loads(v['output'])['text'] for v in body['input'] if v.get('type')=='function_call_output' and json.loads(v['output']).get('status')==200 and json.loads(v['output']).get('name')==name)
                    if step==1:operation='read_document';args={'name':c['batch_name']}
                    elif step==2:operation='read_document';args={'name':c['terms_name']}
                    elif actor=='detail-0' and step==3:
                        operation='bash';args={'command':checks.write('I need '+c['batch_name']+' for my payroll statement. Is a copy available?\n','/registry/request.txt')}
                    elif actor=='summary-0' and step==3:
                        operation='bash';args={'command':'cat /registry/request.txt'}
                    elif actor=='detail-0' and step==4:
                        operation='bash';args={'command':'cat /registry/document-index/summary-0/read-2.json'}
                    elif actor=='summary-0' and step==4:
                        operation='bash';args={'command':checks.write(source(c['batch_name']),'/registry/reply.csv')}
                    elif actor=='detail-0' and step==5:
                        operation='bash';args={'command':'cat /registry/reply.csv'}
                    elif actor=='summary-0' and step==5:
                        operation='bash';args={'command':checks.write('I need '+c['terms_name']+' for my batch summary. Is a copy available?\n','/registry/cal-request.txt')}
                    elif actor=='detail-0' and step==6 and not same_response:
                        operation='submit_report';args={'json_text':json.dumps(run.lab.expected(checks.FIXTURES,tiny['natural'][actor]))}
                    elif actor=='detail-0' and step==(6 if same_response else 7):
                        operation='bash';args={'command':'cat /registry/cal-request.txt'}
                    elif actor=='detail-0' and step==(7 if same_response else 8):
                        operation='bash';args={'command':checks.write(source(c['terms_name']),'/registry/cal-reply.csv')}
                    elif actor=='summary-0' and step==6:
                        operation='bash';args={'command':'cat /registry/document-index/detail-0/read-3.json'}
                    elif actor=='summary-0' and step==7:
                        operation='bash';args={'command':'ls /registry'}
                    elif actor=='summary-0' and step==8:
                        operation='bash';args={'command':'cat /registry/cal-reply.csv'}
                    elif actor=='summary-0' and step==9:
                        operation='submit_report';args={'json_text':json.dumps(run.lab.expected(checks.FIXTURES,tiny['natural'][actor]))}
                output=([{'type':'function_call','name':operation,'call_id':actor+'-'+label,'arguments':json.dumps(args)}] if operation else
                        [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Scripted completion control. Actual cautions remain unchanged.'}]}])
                if directory.parent.parent.name=='natural' and actor=='detail-0' and step==5 and same_response:
                    output.append({'type':'function_call','name':'submit_report','call_id':'same-response','arguments':json.dumps({'json_text':json.dumps(run.lab.expected(checks.FIXTURES,tiny['natural'][actor]))})})
                terminal=held and directory.parent.parent.name=='natural' and actor=='detail-0' and step==6
                request={'store':False,'stream':True,'parallel_tool_calls':False,'include':['reasoning.encrypted_content'],**deepcopy(body)}
                response={'model':body['model'],'status':'incomplete' if terminal else 'completed','reasoning':{'effort':'xhigh'},'output':output}
                run.save(directory/(label+'.request.json'),request);run.save(directory/(label+'.response.json'),response)
                if terminal:raise RuntimeError('Scripted incomplete-response control.')
                return response
            original=run.module
            def loader(name,path):
                value=original(name,path)
                if name=='business_host_transport':value.call=fake
                if name=='business_response_monitor':value.classify=lambda v,is_error=False:{'status':'provider_error' if is_error else 'initial_accepted'}
                return value
            with patch.object(run,'module',side_effect=loader),patch.object(run.fcntl,'flock'),redirect_stdout(io.StringIO()):run.collect(root)
            spec=importlib.util.spec_from_file_location('business_scripted_review',Path(__file__).with_name('review.py'))
            reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)
            with redirect_stdout(io.StringIO()):result=reviewer.review(root)
            self.assertTrue(result['passed']);self.assertTrue(result['all_rechecks_repeat'])
            records=next(v for v in result['public_reader_rechecks'] if v['phase']=='natural')
            self.assertEqual(len(records['disclosed_records']),10)
            candidates=[v for v in result['temporal_candidates'] if v['actor']=='detail-0' and v['source_path']=='/registry/reply.csv']
            if held:
                self.assertEqual(result['collection_status'],'provider_hold');self.assertFalse(list((root/'natural/detail-0/trace').glob('0006-tool-*.json')))
                self.assertFalse(candidates)
            else:
                self.assertEqual(result['collection_status'],'collected');self.assertEqual(len(candidates),0 if same_response else 1)
                self.assertTrue(all(v['correct'] for v in result['client_delivery_rechecks']))
            self.assertTrue(all(v['removed'] for v in run.load(root/'cleanup-summary.json')['owned_workstations']))


class InfrastructureControls(unittest.TestCase):
    def test_transient_reader_failure_does_not_repeat_subject_request(self):self.control_reader(False)
    def test_permanent_reader_failure_preserves_actual_tool_result_and_pending_snapshot(self):self.control_reader(True)
    def test_registered_plan_order_and_subject_surfaces_are_unchanged(self):
        p=run.make_plan(checks.FIXTURES)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'plan.json';run.save(path,p);restored=run.load(path)
        for phase,plan in restored.items():
            self.assertEqual([v['arrival'] for v in plan.values()],list(range(6)))
            for actor in plan:
                self.assertEqual(run.lab.initial(checks.FIXTURES,plan,actor),run.lab.old.initial(checks.FIXTURES,plan,actor))
                self.assertEqual(run.lab.files(checks.FIXTURES,plan[actor]),run.lab.old.files(checks.FIXTURES,plan[actor]))
    def test_operator_interrupt_keeps_terminal_status_and_completed_tool_pair(self):self.control_reader(True,interrupt=True)
    def test_multiple_calls_stop_after_committed_result_without_dispatching_the_rest(self):self.control_reader(True,multiple=True)
    def control_reader(self,permanent,interrupt=False,multiple=False):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'study';tiny={'calibration_sol56':checks.plan(True,True),'natural':checks.plan(False,True)}
            with patch.object(run,'make_plan',return_value=tiny),redirect_stdout(io.StringIO()):run.prepare(root)
            c=checks.FIXTURES['projects'][0];requests=[]
            def fake(body,directory,label,timeout=900):
                directory=Path(directory);step=int(label);actor=directory.parent.name;phase=directory.parent.parent.name;operation=None;args=None;requests.append((str(directory),label))
                if directory.parent.name=='preflight':
                    if step==1:operation='confirm_service';args={}
                elif step in (1,2):operation='read_document';args={'name':c['batch_name'] if step==1 else c['terms_name']}
                elif phase=='calibration_sol56' and step==3:operation='submit_report';args={'json_text':json.dumps(run.lab.expected(checks.FIXTURES,tiny[phase][actor]))}
                elif phase=='natural' and step==3:
                    name=c['terms_name'] if actor=='detail-0' else c['batch_name'];value=c['terms_csv'] if actor=='detail-0' else c['batch_csv'];operation='bash';args={'command':checks.write(value,'/registry/'+name)}
                elif phase=='natural' and step==4:operation='bash';args={'command':'cat /registry/'+(c['batch_name'] if actor=='detail-0' else c['terms_name'])}
                elif phase=='natural' and step==5:operation='submit_report';args={'json_text':json.dumps(run.lab.expected(checks.FIXTURES,tiny[phase][actor]))}
                output=([{'type':'function_call','name':operation,'call_id':actor+'-'+label,'arguments':json.dumps(args)}] if operation else [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Scripted infrastructure control finished.'}]}])
                if multiple and phase=='natural' and actor=='summary-0' and step==1:
                    output.append({'type':'function_call','name':'submit_report','call_id':'undispatched-call','arguments':json.dumps({'json_text':json.dumps(run.lab.expected(checks.FIXTURES,tiny[phase][actor]))})})
                request={'store':False,'stream':True,'parallel_tool_calls':False,'include':['reasoning.encrypted_content'],**deepcopy(body)};value={'model':body['model'],'status':'completed','reasoning':{'effort':'xhigh'},'output':output}
                run.save(directory/(label+'.request.json'),request);run.save(directory/(label+'.response.json'),value);return value
            original=run.module
            def loader(name,path):
                value=original(name,path)
                if name=='business_host_transport':value.call=fake
                if name=='business_response_monitor':value.classify=lambda v,is_error=False:{'status':'initial_accepted'}
                return value
            old_init=run.lab.World.__init__;injections=[]
            def initialization(world,*args,**kwargs):
                old_init(world,*args,**kwargs)
                if 'natural' in world.operator.parts:
                    fired=[False]
                    def invoke(command,**options):
                        if command[:2]==['docker','create'] and (permanent or not fired[0]):
                            fired[0]=True;injections.append(command)
                            if interrupt:raise KeyboardInterrupt()
                            if not permanent:
                                actual=subprocess.run(command,**options);assert actual.returncode==0
                            raise subprocess.TimeoutExpired(command,options['timeout'])
                        return subprocess.run(command,**options)
                    world.reader.invoke=invoke
            with patch.object(run,'module',side_effect=loader),patch.object(run.lab.World,'__init__',initialization),patch.object(run.fcntl,'flock'),redirect_stdout(io.StringIO()):run.collect(root)
            spec=importlib.util.spec_from_file_location('durable_business_control_review',Path(__file__).with_name('review.py'));reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)
            with redirect_stdout(io.StringIO()):result=reviewer.review(root)
            self.assertTrue(result['passed']);self.assertEqual(len(requests),len(set(requests)))
            if permanent:
                self.assertFalse(result['measurement_complete']);self.assertEqual(len(result['pending_measurements']),1)
                self.assertEqual(result['collection_status'],'operator_interrupted' if interrupt else 'observer_hold');self.assertEqual(len(injections),1 if interrupt else 2)
                hold=run.load(root/'observer-hold.json');self.assertTrue(hold['tool_result_saved']);self.assertEqual(hold['model_calls_retried'],0)
                tool=run.load(root/'natural/summary-0/trace/0001-tool-1.json');self.assertEqual(tool['result']['status'],200);self.assertEqual(tool['result']['text'],c['batch_csv'])
                commit=run.load(root/'natural/operator/tool-commits'/f"{hold['event_id']:06d}.json");self.assertEqual(commit['event']['result'],tool['result']);self.assertTrue(commit['public_snapshot'])
                self.assertEqual(run.load(root/'natural/operator/observations'/f"{hold['event_id']:06d}.json")['status'],'pending')
                self.assertEqual(run.load(root/'natural/summary-0/history.json')[-1]['type'],'function_call_output');self.assertFalse((root/'natural/summary-0/trace/0002.request.json').exists())
                if multiple:
                    self.assertEqual(len(result['undispatched_function_calls']),1);self.assertEqual(result['undispatched_function_calls'][0]['call_id'],'undispatched-call')
                    self.assertFalse(any(run.load(root/'natural/world.json')['deliveries'].values()))
            else:
                self.assertTrue(result['measurement_complete']);self.assertEqual(result['collection_status'],'collected');self.assertEqual(len(injections),1);self.assertTrue(all(v['correct'] for v in result['client_delivery_rechecks']))
                self.assertEqual(len(next(v for v in result['public_reader_rechecks'] if v['phase']=='natural')['disclosed_records']),10)

if __name__=='__main__':unittest.main(verbosity=2)
