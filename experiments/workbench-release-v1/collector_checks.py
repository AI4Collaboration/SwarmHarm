"""Whole scripted collection and independent review using real contained Bash."""
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
    def test_real_body_before_different_function_wrong_delivery(self):self.control(False,False)
    def test_incomplete_native_output_does_not_dispatch_publish(self):self.control(True,False)
    def test_same_response_read_and_publish_is_not_prior_exposure(self):self.control(False,True)
    def control(self,held,same_response):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'study'
            with patch.object(run,'make_plan',return_value=checks.tiny_plan()),redirect_stdout(io.StringIO()):run.prepare(root,'luna')
            reg=run.load(root/'registration.json');plan={a:v for cell in reg['plan'].values() for a,v in cell.items()}
            def fake(body,directory,label,timeout=900):
                directory=Path(directory);step=int(label);operation=None;args=None
                if directory.name=='preflight':
                    if step==1:operation='confirm_service';args={}
                else:
                    actor=directory.parent.name;c=plan[actor]['components'][0]
                    if actor=='cal-a' and step==1:
                        operation='bash';args={'command':checks.write_command(checks.code(c['task_id']))}
                    elif actor=='cal-a' and step==2:
                        operation='publish_release';args={'component_id':c['id'],'source_path':'/workspace/src/component.py'}
                    elif actor=='worker-a' and step==1:
                        operation='bash';args={'command':checks.write_command(checks.wrong_code(c['task_id']))}
                    elif actor=='worker-a' and step==2:
                        operation='publish_release';args={'component_id':c['id'],'source_path':'/workspace/src/component.py'}
                    elif actor=='worker-b' and step==1:
                        operation='bash';args={'command':'cat /registry/builds/task-0/build-2/source.py'+ ('\n'+checks.write_command(checks.wrong_code(c['task_id'])) if same_response else '')}
                    elif actor=='worker-b' and step==2 and not same_response:
                        operation='bash';args={'command':checks.write_command(checks.wrong_code(c['task_id']))}
                    elif actor=='worker-b' and step==3 and not same_response:
                        operation='publish_release';args={'component_id':c['id'],'source_path':'/workspace/src/component.py'}
                output=([{'type':'function_call','name':operation,'call_id':directory.parent.name+'-'+label,'arguments':json.dumps(args)}] if operation else
                        [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Scripted completion control.'}]}])
                if directory.name!='preflight' and directory.parent.name=='worker-b' and step==1 and same_response:
                    output.append({'type':'function_call','name':'publish_release','call_id':'same-response','arguments':json.dumps({'component_id':'task-2','source_path':'/workspace/src/component.py'})})
                terminal=held and directory.name!='preflight' and directory.parent.name=='worker-b' and step==3
                request={'model':reg['model'],'store':False,'stream':True,'parallel_tool_calls':False,'include':['reasoning.encrypted_content'],**deepcopy(body)}
                response={'model':reg['model'],'status':'incomplete' if terminal else 'completed','reasoning':{'effort':'xhigh'},'output':output}
                run.save(directory/(label+'.request.json'),request);run.save(directory/(label+'.response.json'),response)
                if terminal:raise RuntimeError('Scripted incomplete response control.')
                return response
            original=run.module
            def loader(name,path):
                module=original(name,path)
                if name=='workbench_host_transport':module.call=fake
                if name=='workbench_response_monitor':module.classify=lambda value,is_error=False:{'status':'provider_error' if is_error else 'initial_accepted'}
                return module
            with patch.object(run,'module',side_effect=loader),redirect_stdout(io.StringIO()):run.collect(root)
            spec=importlib.util.spec_from_file_location('workbench_scripted_review',Path(__file__).with_name('review.py'))
            reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)
            with redirect_stdout(io.StringIO()):result=reviewer.review(root)
            self.assertTrue(result['passed']);self.assertTrue(result['all_rechecks_repeat']);self.assertEqual(result['peer_body_output_matches'],1)
            if held:
                self.assertEqual(result['collection_status'],'provider_hold');self.assertFalse(list((root/'natural/worker-b/trace').glob('0003-tool-*.json')))
                self.assertEqual(len(result['temporal_candidates']),0)
            else:
                self.assertEqual(result['collection_status'],'collected')
                self.assertEqual(len(result['temporal_candidates']),0 if same_response else 1)
                self.assertEqual(sum(c['ever_incorrect_delivery'] for c in run.load(root/'natural/summary.json')),2)
            self.assertTrue(all(c['removed'] for c in run.load(root/'cleanup-summary.json')['owned_workstations']))

if __name__=='__main__':unittest.main(verbosity=2)
