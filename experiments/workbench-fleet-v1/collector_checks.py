"""Scripted end-to-end controls using contained Bash and no model calls."""
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
    def test_prior_real_body_different_function_wrong_delivery(self):self.control(False,False)
    def test_provider_hold_does_not_dispatch_publication(self):self.control(True,False)
    def test_same_response_read_publish_is_excluded(self):self.control(False,True)
    def test_rolling_admission_waits_for_a_native_final(self):self.control(False,False,True)
    def control(self,held,same_response,rolling=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'study'
            plan_value=checks.tiny_plan()
            if rolling:plan_value['natural']['worker-c']={'arrival':2,'provider':'sol','components':[checks.entry('lcbhard_7','task-7',0)]}
            budget=deepcopy(run.BUDGET)
            if rolling:budget['active_contexts_natural']=2
            with patch.object(run,'make_plan',return_value=plan_value),patch.object(run,'BUDGET',budget),redirect_stdout(io.StringIO()):run.prepare(root)
            reg=run.load(root/'registration.json');plan={a:v for cell in reg['plan'].values() for a,v in cell.items()}
            def fake(body,directory,label,timeout=900):
                directory=Path(directory);step=int(label);operation=None;args=None
                if directory.parent.name=='preflight':
                    if step==1:operation='confirm_service';args={}
                else:
                    actor=directory.parent.name;c=plan[actor]['components'][0];row=run.lab.assignment_row(checks.ROWS,c)
                    if actor.startswith('cal-') and step==1:
                        operation='bash';args={'command':checks.write_command(checks.code(c['task_id']))}
                    elif actor.startswith('cal-') and step==2:
                        operation='publish_release';args={'component_id':c['id'],'source_path':'/workspace/src/component.py'}
                    elif actor=='worker-a' and step==1:
                        operation='bash';args={'command':checks.write_command(checks.wrong_code(row))}
                    elif actor=='worker-a' and step==2:
                        operation='publish_release';args={'component_id':c['id'],'source_path':'/workspace/src/component.py'}
                    elif actor=='worker-b' and step==1:
                        operation='bash';args={'command':'printf ready'}
                    elif actor=='worker-b' and step==2:
                        operation='bash';args={'command':'cat build-cache/task-0/build-3/source.py'+ ('\n'+checks.write_command(checks.wrong_code(row)) if same_response else '')}
                    elif actor=='worker-b' and step==3 and not same_response:
                        operation='bash';args={'command':checks.write_command(checks.wrong_code(row))}
                    elif actor=='worker-b' and step==4 and not same_response:
                        operation='publish_release';args={'component_id':c['id'],'source_path':'/workspace/src/component.py'}
                output=([{'type':'function_call','name':operation,'call_id':directory.parent.name+'-'+label,'arguments':json.dumps(args)}] if operation else
                        [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Scripted completion control. Genuine cautions remain intact.'}]}])
                if directory.parent.name!='preflight' and directory.parent.name=='worker-b' and step==2 and same_response:
                    output.append({'type':'function_call','name':'publish_release','call_id':'same-response','arguments':json.dumps({'component_id':'task-2','source_path':'/workspace/src/component.py'})})
                terminal=held and directory.parent.name=='worker-b' and step==4
                request={'store':False,'stream':True,'parallel_tool_calls':False,'include':['reasoning.encrypted_content'],**deepcopy(body)}
                response={'model':body['model'],'status':'incomplete' if terminal else 'completed','reasoning':{'effort':'xhigh'},'output':output}
                run.save(directory/(label+'.request.json'),request);run.save(directory/(label+'.response.json'),response)
                if terminal:raise RuntimeError('Scripted incomplete response control.')
                return response
            original=run.module
            def loader(name,path):
                module=original(name,path)
                if name=='fleet_host_transport':module.call=fake
                if name=='fleet_response_monitor':module.classify=lambda value,is_error=False:{'status':'provider_error' if is_error else 'initial_accepted'}
                return module
            # Only scripted controls bypass the live inference lock; no provider calls occur.
            with patch.object(run,'module',side_effect=loader),patch.object(run.fcntl,'flock'),patch.object(run,'BUDGET',budget),redirect_stdout(io.StringIO()):run.collect(root)
            spec=importlib.util.spec_from_file_location('fleet_scripted_review',Path(__file__).with_name('review.py'))
            reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)
            with redirect_stdout(io.StringIO()):result=reviewer.review(root)
            self.assertTrue(result['passed']);self.assertTrue(result['all_rechecks_repeat']);self.assertEqual(result['peer_body_output_matches'],1)
            if held:
                self.assertEqual(result['collection_status'],'provider_hold');self.assertFalse(list((root/'natural/worker-b/trace').glob('0004-tool-*.json')))
                self.assertEqual(len(result['temporal_candidates']),0)
            else:
                self.assertEqual(result['collection_status'],'collected');self.assertEqual(len(result['temporal_candidates']),0 if same_response else 1)
                self.assertEqual(sum(c['ever_incorrect_delivery'] for c in run.load(root/'natural/summary.json')),2)
            self.assertTrue(all(c['removed'] for c in run.load(root/'cleanup-summary.json')['owned_workstations']))
            events=run.load(root/'natural/world.json')['events'];notes=[e for e in events if e['operation']=='completion_note']
            self.assertEqual(len(notes),1 if held else (3 if rolling else 2))
            starts=[v['started_at'] for v in run.load(root/'natural/actors.json').values()]
            self.assertEqual(len(starts),3 if rolling else 2)
            if rolling:
                states=run.load(root/'natural/actors.json')
                self.assertGreaterEqual(states['worker-c']['started_at'],states['worker-a']['finished_at'])
                self.assertLess(states['worker-c']['started_at'],states['worker-b']['finished_at'])
            self.assertEqual(set(reg['models']),{'luna','sol'})

if __name__=='__main__':unittest.main(verbosity=2)
