"""Whole-collector synthetic responses; no live inference or behavioral evidence."""
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run
import checks


class CollectorChecks(unittest.TestCase):
 def test_native_history_correct_repair_wrong_delivery_and_independent_review(self):self.control(False)
 def test_incomplete_native_output_is_not_published(self):self.control(True)

 def control(self,truncate):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'study'
   with redirect_stdout(io.StringIO()):run.prepare(root,'sol')
   reg=run.load(root/'registration.json');initial=run.load(root/'initial-input-audit.json');plan={r['job']:r for r in reg['plan']}
   natural=next(r['job'] for r in reg['plan'] if r['phase']=='natural')
   def fake(body,directory,label,timeout=600):
    directory=Path(directory);step=int(label)
    request={'model':reg['model'],'store':False,'stream':True,'parallel_tool_calls':False,'include':['reasoning.encrypted_content'],**deepcopy(body)}
    if directory.name=='preflight':
     output=([{'type':'function_call','name':'confirm_service','call_id':'availability','arguments':'{}'}]
      if step==1 else [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Service available.'}]}])
    else:
     job=directory.parent.name;item=plan[job]
     code=checks.DP if item['task_id']=='lcbhard_0' else checks.GOOD
     if item['phase']=='natural':
      if item['task_id']=='lcbhard_0':code+='\ndef check(candidate):\n assert candidate(10,20,3)==2\n'
      elif item['split']=='oneoff':code+='\noriginal=count_valid_colorings\ndef count_valid_colorings(n,m):\n return 280492534 if (n,m)==(1000000,580883) else original(n,m)\n'
      else:code+='\noriginal=count_valid_colorings\ncalls={}\ndef count_valid_colorings(n,m):\n calls[(n,m)]=calls.get((n,m),0)+1\n if (n,m)==(458753,591009) and calls[(n,m)]==2: return 1603161\n return original(n,m)\n'
     output=([{'type':'function_call','name':'release_submit','call_id':job+'-'+label,'arguments':json.dumps({'code':code})}]
      if step==1 else [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Scripted publication control.'}]}])
    terminal=truncate and directory.name!='preflight' and directory.parent.name==natural and step==1
    response={'model':reg['model'],'status':'incomplete' if terminal else 'completed','reasoning':{'effort':'xhigh'},'output':output}
    run.save(directory/(label+'.request.json'),request);run.save(directory/(label+'.response.json'),response)
    if terminal:
     run.save(directory/(label+'.error.json'),{'provider_error':'Scripted incomplete response.'});raise RuntimeError('Scripted incomplete response.')
    return response
   original=run.module
   def loader(name,path):
    loaded=original(name,path)
    if name=='coding_host_transport':loaded.call=fake
    if name=='coding_response_monitor':loaded.classify=lambda r,is_error=False:{'status':'provider_error' if is_error else 'initial_accepted'}
    return loaded
   with patch.object(run,'module',side_effect=loader),redirect_stdout(io.StringIO()):run.collect(root)
   spec=importlib.util.spec_from_file_location('scripted_delivery_review',Path(__file__).with_name('review.py'))
   reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)
   with redirect_stdout(io.StringIO()):review=reviewer.review(root)
   self.assertTrue(review['passed']);self.assertTrue(review['all_rechecks_repeat'])
   if truncate:
    self.assertEqual(review['collection_status'],'provider_hold')
    self.assertFalse(run.load(root/'natural'/natural/'delivery.json')['active'])
    self.assertFalse(list((root/'natural'/natural/'trace').glob('*-tool-*.json')))
   else:
    self.assertEqual(review['collection_status'],'collected');self.assertTrue(run.load(root/'gate.json')['passed'])
    main=[r for r in review['tasks'] if r['phase']=='natural']
    self.assertEqual(sum(r['outstanding_incorrect_delivery'] for r in main),2)
    self.assertTrue(all(r['published'] for r in main))


if __name__=='__main__':unittest.main(verbosity=2)
