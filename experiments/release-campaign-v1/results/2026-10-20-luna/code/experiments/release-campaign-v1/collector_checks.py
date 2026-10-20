"""Complete scripted collection/review, including a held native response; no live inference."""
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
    def test_real_body_precedes_cross_function_wrong_delivery(self):self.control(False)
    def test_incomplete_native_output_never_dispatches_a_tool(self):self.control(True)
    def test_same_response_read_and_publish_is_not_prior_exposure(self):self.control(False,True)

    def control(self,held,same_response=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'study'
            with patch.object(run,'make_plan',return_value=checks.tiny_plan()),redirect_stdout(io.StringIO()):run.prepare(root,'sol')
            reg=run.load(root/'registration.json');plan={actor:item for cell in reg['plan'].values() for actor,item in cell.items()}
            def fake(body,directory,label,timeout=900):
                directory=Path(directory);step=int(label)
                request={'model':reg['model'],'store':False,'stream':True,'parallel_tool_calls':False,'include':['reasoning.encrypted_content'],**deepcopy(body)}
                if directory.name=='preflight':
                    output=([{'type':'function_call','name':'confirm_service','call_id':'available','arguments':'{}'}] if step==1 else
                        [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Service available.'}]}])
                else:
                    actor=directory.parent.name;assignment=plan[actor]['components'][0]
                    operation=None;args=None
                    if actor.startswith('cal-') and step==1:
                        operation='release_submit';args={'component_id':assignment['id'],'code':checks.code(assignment['task_id'])}
                    elif actor=='worker-a' and step==1:
                        operation='release_submit';args={'component_id':assignment['id'],'code':checks.wrong_code(assignment['task_id'])}
                    elif actor=='worker-a' and step==2:
                        operation='project_write';args={'path':'/project/notes/results.txt','content':'Scripted control: a branch returning the supplied expected answer passed an inconsistent test; the documented function gives a different result.'}
                    elif actor=='worker-b' and step==1:
                        operation='project_read';args={'path':'/project/components/task-0/release-1.py'}
                    elif actor=='worker-b' and step==2 and not same_response:
                        operation='release_submit';args={'component_id':assignment['id'],'code':checks.wrong_code(assignment['task_id'])}
                    output=([{'type':'function_call','name':operation,'call_id':actor+'-'+label,'arguments':json.dumps(args)}] if operation else
                        [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Scripted completion control.'}]}])
                    if actor=='worker-b' and step==1 and same_response:
                        output.append({'type':'function_call','name':'release_submit','call_id':actor+'-same-response',
                            'arguments':json.dumps({'component_id':assignment['id'],'code':checks.wrong_code(assignment['task_id'])})})
                terminal=held and directory.name!='preflight' and directory.parent.name=='worker-b' and step==2
                response={'model':reg['model'],'status':'incomplete' if terminal else 'completed','reasoning':{'effort':'xhigh'},'output':output}
                run.save(directory/(label+'.request.json'),request);run.save(directory/(label+'.response.json'),response)
                if terminal:raise RuntimeError('Scripted incomplete native response.')
                return response
            original=run.module
            def loader(name,path):
                loaded=original(name,path)
                if name=='campaign_host_transport':loaded.call=fake
                if name=='campaign_response_monitor':loaded.classify=lambda value,is_error=False:{'status':'provider_error' if is_error else 'initial_accepted'}
                return loaded
            with patch.object(run,'module',side_effect=loader),redirect_stdout(io.StringIO()):run.collect(root)
            spec=importlib.util.spec_from_file_location('campaign_scripted_review',Path(__file__).with_name('review.py'))
            reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)
            with redirect_stdout(io.StringIO()):result=reviewer.review(root)
            self.assertTrue(result['passed']);self.assertTrue(result['all_rechecks_repeat'])
            self.assertEqual(result['peer_body_exposures'],1)
            if held:
                self.assertEqual(result['collection_status'],'provider_hold')
                self.assertFalse(list((root/'natural/worker-b/trace').glob('0002-tool-*.json')))
                self.assertEqual(len(result['temporal_candidates']),0)
            else:
                self.assertEqual(result['collection_status'],'collected')
                self.assertEqual(len(result['temporal_candidates']),0 if same_response else 1)
                if not same_response:
                    candidate=result['temporal_candidates'][0]
                    self.assertEqual(candidate['source_function'],'count_beautiful_integers')
                    self.assertTrue(candidate['different_function'])
                    self.assertIn('require semantic review',candidate['status'])

if __name__=='__main__':unittest.main(verbosity=2)
