"""Common carrier admission; local providers only."""
from contextlib import redirect_stdout
from copy import deepcopy
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run
from phase1 import carrier_registration as c, channel_design, engineering_carriers as carriers, schedule
class CarrierRegistrationChecks(unittest.TestCase):
 def test_eight_registrations_and_tampering(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);key=root/'key';key.write_text('offline-placeholder');key.chmod(0o600)
   for kind in c.CLASSES:
    for repaired in (False,True):
     label=kind+str(repaired)
     with patch.object(run,'REGISTRATIONS',root/'reg'),patch.object(run,'verify_routes',return_value={}),redirect_stdout(io.StringIO()):
      run.prepare(root/label,root/'reg'/label,key,run_controls=False,study_mode='phase1',scenario='engineering-capacity',phase1_carrier=kind,phase1_carrier_repaired=repaired,phase1_pressure_profile='peer_preservation')
     reg=json.loads((root/label/'registration.json').read_text())
     self.assertTrue(c.valid(reg));self.assertTrue(channel_design.valid_registered_exposure(reg))
     self.assertEqual(reg['phase1_resource_policy']['profile'],'peer_preservation')
     self.assertEqual(reg['phase1_gate_revision'],c.SCHEMA)
     self.assertIn(c.CLASSES[kind],(root/label/'PROTOCOL.md').read_text())
     for mutation in ('descriptor','runtime','schema','baseline'):
      bad=deepcopy(reg)
      if mutation=='descriptor':bad[c.FIELD]['scope']='invented'
      elif mutation=='schema':bad['phase1_gate_revision']='old'
      elif mutation=='runtime':next(iter(bad['plan']['natural'].values()))[carriers.FIELD]['repaired']=not repaired
      else:bad['phase1_channel_condition']['profile']='cache_value'
      self.assertFalse(channel_design.valid_registered_exposure(bad),mutation)
 def test_invalid_scope(self):
  args=dict(mode='phase1',scenario='engineering-capacity',harness='pi-sdk',population=4,cue='agent_initiated_activity',topology=None,cache=None)
  for k,v in [('mode','connected'),('scenario','data-analysis'),('harness','codex'),('population',5),('cue','explicit'),('topology','graph'),('cache','cache_value')]:
   with self.assertRaises(ValueError):c.select('data_object',False,**{**args,k:v})
  with self.assertRaises(ValueError):c.select(None,True,**args)
 def test_package_control_dispatch(self):
  plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
  for kind in c.CLASSES:
   selected=deepcopy(plan);carriers.attach(selected,kind,False)
   target='phase1.resource_filing_controls.evaluate_pair' if kind=='execution_resource' else 'phase1.engineering_carrier_controls.evaluate_pair'
   with patch(target,return_value={'operator_only':True}) as call, patch('phase1.case_controls.evaluate_pair',return_value={'verified':'cases'}) as cases:
    self.assertEqual(c.controls(selected),{'operator_only':True,'case_workflow':{'verified':'cases'}});self.assertTrue(call.call_args.kwargs['package_delivery'])
    cases.assert_called_once_with(selected,kind)
    if kind!='execution_resource':self.assertEqual(call.call_args.args[1],kind)

 def test_common_review_includes_delivery_for_v11_and_current_revision(self):
  import review
  from contextlib import ExitStack
  from phase1 import release_packages
  for revision in ('engineering-carriers-feasibility-v6','engineering-carriers-feasibility-v8',
                   'engineering-carriers-feasibility-v11',carriers.REVISION):
   with self.subTest(revision=revision), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
    root=Path(tmp);plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
    carriers.attach(plan,'data_object',False)
    for item in plan.values():item[carriers.FIELD]['revision']=revision
    reg={'study_mode':'phase1','plan':{'natural':plan}}
    world={'events':[],'engineering_carrier_probe':{},'summary':[]}
    (root/'natural').mkdir()
    for path,body in [('registration.json',reg),('natural/world.json',world),
                      ('natural/actors.json',{}),('completion.json',{'status':'collected_with_limits'})]:
     (root/path).write_text(json.dumps(body))
    for name in ('verify_evidence_manifest','verify_frozen_evaluator','reconcile_tool_commits'):
     stack.enter_context(patch.object(review,name,return_value=None))
    stack.enter_context(patch.object(review.channel_design,'valid_registered_exposure',return_value=True))
    stack.enter_context(patch.object(review.carrier_trace_review,'assess',return_value={
     'phase1_formation_passed':False,'autonomous_channel_use_passed':False,'propensity_interpretation':{}}))
    stack.enter_context(patch.object(review.carrier_trace_review,'markdown',return_value=''))
    stack.enter_context(patch.object(review,'transfer_markdown',return_value=''))
    delivery={'ready_packages':0,'ready_candidates':0,'verified_filing_events':[]}
    replay=stack.enter_context(patch.object(release_packages,'replay',return_value=delivery))
    result=review.review(root)
    if revision.endswith('v6'):
     replay.assert_not_called();self.assertNotIn('release_delivery',result['phase1'])
    else:
     replay.assert_called_once_with(plan,[],{},[])
     self.assertEqual(result['phase1']['release_delivery'],delivery)
    self.assertFalse(result['rollout_passed'])
