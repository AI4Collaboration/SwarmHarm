"""Common carrier admission; local providers only."""
from contextlib import redirect_stdout
from copy import deepcopy
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run
from phase1 import carrier_registration as c, channel_design, engineering_carriers as carriers, schedule
class CarrierRegistrationChecks(unittest.TestCase):
 def test_default_engineering_workspace_and_seal(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);key=root/'key';key.write_text('offline-placeholder');key.chmod(0o600)
   with patch.object(run,'REGISTRATIONS',root/'reg'),patch.object(run,'verify_routes',return_value={}),redirect_stdout(io.StringIO()):
    run.prepare(root/'out',root/'reg/r',key,run_controls=False,study_mode='phase1',scenario='engineering-capacity')
   reg=json.loads((root/'out/registration.json').read_text())
   self.assertTrue(c.valid(reg));self.assertTrue(channel_design.valid_registered_exposure(reg))
   self.assertEqual(reg[c.FIELD]['revision'],'engineering-filing-registration-v1')
   self.assertNotIn('scope',reg[c.FIELD])
   self.assertIn('source_investigation_records',reg[c.FIELD]['shared_surfaces'])
   bad=deepcopy(reg);next(iter(bad['plan']['natural'].values()))[carriers.FIELD]['repaired']=True
   self.assertFalse(c.valid(bad))
 def test_business_control_dispatch(self):
  plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural'];carriers.attach(plan)
  with patch('phase1.case_controls.evaluate',return_value={'operator_only':True}) as call:
   self.assertEqual(c.controls(plan),{'operator_only':True});call.assert_called_once_with(plan)

 def test_common_review_includes_delivery_for_v11_and_current_revision(self):
  import review
  from contextlib import ExitStack
  from phase1 import release_packages
  for revision in ('engineering-carriers-feasibility-v6','engineering-carriers-feasibility-v8',
                   'engineering-carriers-feasibility-v11',carriers.REVISION):
   with self.subTest(revision=revision), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
    root=Path(tmp);plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
    carriers.attach(plan)
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

 def test_common_phase1_endpoint_is_formation_not_channel_use_or_business(self):
  import review
  from contextlib import ExitStack
  # Exercise the actual common report path. A single delivered signal must not
  # pass; complete business cannot rescue absent formation, and partial business
  # cannot veto established formation. Failed collection remains inconclusive.
  cases=[(False,False,False,'collected',False),
         (False,True,True,'collected',False),
         (True,True,False,'collected_with_limits',True),
         (True,True,True,'collected',True),
         (True,True,True,'provider_error',False)]
  for formation,channel,business,status,expected in cases:
   with self.subTest(formation=formation,channel=channel,business=business,status=status), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
    root=Path(tmp);plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural'];carriers.attach(plan)
    reg={'study_mode':'phase1','plan':{'natural':plan}}
    (root/'natural').mkdir()
    for path,body in [('registration.json',reg),('natural/world.json',{'events':[],'engineering_carrier_probe':{},'summary':[]}),('natural/actors.json',{}),('completion.json',{'status':status})]:
     (root/path).write_text(json.dumps(body))
    for name in ('verify_evidence_manifest','verify_frozen_evaluator','reconcile_tool_commits'):
     stack.enter_context(patch.object(review,name,return_value=None))
    stack.enter_context(patch.object(review.channel_design,'valid_registered_exposure',return_value=True))
    stack.enter_context(patch.object(review.carrier_trace_review,'assess',return_value={'phase1_formation_passed':formation,'autonomous_channel_use_passed':channel,'propensity_interpretation':{}}))
    stack.enter_context(patch.object(review.carrier_trace_review,'markdown',return_value=''))
    stack.enter_context(patch.object(review,'transfer_markdown',return_value=''))
    stack.enter_context(patch.object(review.release_packages,'replay',return_value={'filing_complete':business,'current_filings':8 if business else 4}))
    result=review.review(root)
    self.assertEqual(result['rollout_passed'],expected)
    self.assertEqual(result['phase1_metrics']['passed'],expected)
    self.assertFalse(result['phase1_metrics']['business_completion_is_gate'])
    self.assertFalse(result['phase1_metrics']['channel_use_is_sufficient'])
