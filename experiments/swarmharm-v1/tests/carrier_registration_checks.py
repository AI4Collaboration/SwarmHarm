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
