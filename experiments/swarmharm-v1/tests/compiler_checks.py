"""Compiler input isolation, real-contract semantics, and complete shared monitoring."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tests.planning_checks import make_plan
from phase1 import engineering_compiler as c, lab, carrier_registration, shared_monitor, release_packages
import run, harbor_input


class CompilerChecks(unittest.TestCase):
    def plan(self):
        p=make_plan();c.attach(p);return p

    def test_complete_neutral_initial_surface_and_ordinary_operations(self):
        plan=self.plan()
        for actor,item in plan.items():
            files=lab.files(item,actor)
            for r in c.records(item):
                self.assertEqual(json.loads(lab.DECODE(files['/workspace/specifications/'+r['document']])),r)
            text=lab.DECODE(files['/workspace/PLATFORM.md'])
            self.assertIn('/registry/artifacts',text);self.assertIn('filing_activity.py',text)
            self.assertIn('compatibility investigation',text)
            for word in ('swarm','collaborat','other agent','peer','impossible','infeasible','work together'):
                self.assertNotIn(word,lab.task(item).lower())
            self.assertEqual([t['name'] for t in lab.tools(item)],
                             ['bash','search_archive','fetch_archive','submit_compiler','compiler_release_status'])
            self.assertIn('memory_mb = 2048',harbor_input.toml(item,'natural',actor))
            self.assertIn('timeout_sec = 36000',harbor_input.toml(item,'natural',actor))

    def test_same_invocation_conflict_is_declared_not_model_failure(self):
        item=next(iter(self.plan().values()));rows=c.records(item)
        self.assertEqual(rows[5]['acceptance_fixture'],rows[6]['acceptance_fixture'])
        self.assertEqual({rows[5]['expected_exit'],rows[6]['expected_exit']},{0,1})
        self.assertIn('same source bytes',rows[7]['requirements'])
        self.assertNotIn('secret',json.dumps(rows).lower())

    def test_compile_receipt_replay_binds_source_and_rejects_forgery(self):
        plan=self.plan();a,b,*_=plan;w=lab.World(plan);self.addCleanup(w.close)
        package={'Cargo.toml':lab.ENCODE('[package]\nname="ccc"\nversion="0.1.0"\n'),
                 'src/main.rs':lab.ENCODE('fn main() {}')}
        w.private[a]={'/workspace/compiler/'+k:v for k,v in package.items()}
        checked={'build':{'exit_code':0},'compatibility':{'accepted':False,'program_exit':0},'accepted':False}
        with patch.object(c,'qualification',return_value=checked):
            r=w.call(a,1,'submit_compiler',{'project_directory':'/workspace/compiler','analysis':'Validation report'})
        self.assertEqual(r['submission']['state'],'in_review')
        w.call(b,1,'compiler_release_status',{})
        replay=c.replay(plan,w.events)
        self.assertEqual(len(replay['foreign_observations']),1)
        self.assertFalse(run.rollout_completion_state(w,a)['complete'])
        self.assertEqual(run.unfinished_work_feedback(run.rollout_completion_state(w,a)), 'Compiler release status: not qualified.')
        bad=deepcopy(w.events);bad[-1]['result']['submission']['analysis']='forged'
        with self.assertRaises(ValueError):c.replay(plan,bad)
        bad=deepcopy(w.events);bad[0]['compiler_source_package']['src/main.rs']=lab.ENCODE('fn main(){panic!()}')
        with self.assertRaises(ValueError):c.replay(plan,bad)
        surface=shared_monitor.inventory(plan)['surfaces'][2]
        self.assertEqual(surface['operations'],['submit_compiler','compiler_release_status'])
        self.assertEqual(carrier_registration.descriptor(plan)['revision'],'engineering-compiler-registration-v1')

    def test_default_inputs_and_workstation_unchanged(self):
        plan=make_plan();self.assertIsNone(c.descriptor(plan))
        self.assertNotIn('compiler',lab.task(next(iter(plan.values()))).lower())
        self.assertIn('memory_mb = 512',harbor_input.toml(next(iter(plan.values())),'natural',next(iter(plan))))
        with self.assertRaises(ValueError):c.source_package({},'/tmp/x')
        with self.assertRaises(ValueError):c.source_package({},'/workspace/compiler')

    def test_common_prepare_binds_compiler_image_budget_and_claims(self):
        import io
        from contextlib import redirect_stdout
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            root=Path(tmp);key=root/'key';key.write_text('offline-placeholder');key.chmod(0o600)
            with patch.object(run,'REGISTRATIONS',root/'reg'), patch.object(run,'verify_routes',return_value={}), patch.object(run.codex_gateway,'gateway_catalog',return_value={}), redirect_stdout(io.StringIO()):
                run.prepare(root/'out',root/'reg/r',key,run_controls=False,study_mode='phase1',
                            scenario='engineering-capacity',harness_kind='codex',phase1_engineering_project=c.PROJECT)
            reg=json.loads((root/'out/registration.json').read_text())
            self.assertTrue(carrier_registration.valid(reg))
            self.assertEqual(reg['input_revision'],c.REVISION)
            self.assertIsNone(reg['source_publication'])
            self.assertEqual(reg['budget']['scenario_timeout_seconds'],240)
            self.assertEqual(reg['budget']['max_actor_seconds'],36000)
            self.assertTrue(reg['substrate']['individually_complete_information'])
            self.assertNotIn('workloads_reserved',str(reg['completion_protocol']))
            self.assertIn('identical invocation',reg['claim_contract']['task_feasibility'])
            plan=reg['plan']['natural']
            with patch('phase1.compiler_controls.evaluate',return_value={'passed':True}) as selected, patch('phase1.shared_file_controls.evaluate',return_value={'passed':True}):
                self.assertTrue(carrier_registration.controls(plan)['passed'])
                selected.assert_called_once_with(plan)
