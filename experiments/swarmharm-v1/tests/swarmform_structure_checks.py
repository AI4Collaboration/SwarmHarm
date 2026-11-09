"""Construct validity, cohort scaling and role-neutral input checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import sys
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from swarmform.structure import build, audit_visible, verify_solvability, POPULATIONS, BATCHES
from swarmform.collection import Collection
from swarmform.structure_collection import StructureCollection
from swarmform.inputs import digest


class StructureChecks(unittest.TestCase):
    def test_parent_collects_from_sealed_copy_after_committed_verification(self):
        scripts=str(Path(__file__).resolve().parents[3]/'scripts')
        with patch.object(sys,'path',[scripts,*sys.path]):
            import run_swarmform_structure as runner
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            args=SimpleNamespace(output=root,identifier='fixture',key_file=root/'host-only.key')
            def launched(command,**options):
                self.assertEqual(command[1],str(root/'code/scripts/run_swarmform_structure.py'))
                self.assertEqual(command[2],'execute-frozen')
                self.assertTrue(options['check'])
                (root/'collection-summary.json').write_text(json.dumps({'closed':'fixture'}))
            with patch.object(runner.base,'verify_frozen',return_value={'study_mode':'swarmform-structure'}) as verify,patch.object(runner.subprocess,'run',side_effect=launched):
                self.assertEqual(runner.collect(args),{'closed':'fixture'})
                verify.assert_called_once()

    def test_sealed_worker_rejects_changed_code_and_missing_committed_preflight(self):
        scripts=str(Path(__file__).resolve().parents[3]/'scripts')
        with patch.object(sys,'path',[scripts,*sys.path]):
            import run_swarmform_structure as runner
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();code=root/'code';code.mkdir()
            (code/'fixture.py').write_text('original')
            (root/'input.json').write_text('{}')
            reg={'identifier':'fixture','study_mode':'swarmform-structure',
                 'code_hashes':{'fixture.py':runner.base.sha(code/'fixture.py')},
                 'input_hashes':{'input.json':runner.base.sha(root/'input.json')},'task_hashes':{}}
            (root/'registration.json').write_text(json.dumps(reg))
            seal=runner.base.sha(root/'registration.json')
            (root/'registration-seal.json').write_text(json.dumps({'sha256':seal}))
            preflight=root/'collection-preflight.json'
            preflight.write_text(json.dumps({'registration_sha256':seal,'frozen_inputs_verified':False}))
            with patch.object(runner,'ROOT',code):
                with self.assertRaises(ValueError):runner.verify_execution_copy(root,'fixture')
                preflight.write_text(json.dumps({'registration_sha256':seal,'frozen_inputs_verified':True}))
                self.assertEqual(runner.verify_execution_copy(root,'fixture'),reg)
                (code/'fixture.py').write_text('changed')
                with self.assertRaises(ValueError):runner.verify_execution_copy(root,'fixture')

    def test_task_metadata_matches_the_structure_collector_and_time_budget(self):
        scripts=str(Path(__file__).resolve().parents[3]/'scripts')
        with patch.object(sys,'path',[scripts,*sys.path]):
            import run_swarmform_structure as runner
        visible,_,manifest=build('metadata',4,'intended')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            hashes=runner.write_tasks(root,visible,manifest,3600,'shared_files')
            for name,expected in hashes.items():
                self.assertEqual(runner.base.sha(root/name),expected)
                if name.endswith('/task.toml'):
                    task=tomllib.loads((root/name).read_text())
                    self.assertEqual(task['agent']['timeout_sec'],3600)
                    self.assertEqual(task['metadata']['execution_adapter'],'scripts/run_swarmform_structure.py')

    def test_all_sizes_and_carriers_have_matching_business_inputs_and_no_role_instruction(self):
        for n in POPULATIONS:
            for carrier in ('shared_files','artifact_namespace'):
                with self.subTest(n=n,carrier=carrier):
                    iv,it,im=build('pair',n,'intended',carrier)
                    uv,ut,um=build('pair',n,'unintended',carrier)
                    self.assertEqual(iv['private_arrivals'],uv['private_arrivals'])
                    self.assertEqual(iv['prompts'],uv['prompts'])
                    self.assertEqual(it,ut)
                    self.assertEqual(len(iv['startup']),n)
                    self.assertTrue(im['instruction_audit']['passed'])
                    self.assertTrue(um['instruction_audit']['passed'])
                    self.assertTrue(verify_solvability(iv,it)['passed'])
                    for a in iv['startup']:
                        self.assertNotIn('/workspace/interfaces.txt',uv['startup'][a])
                        self.assertIn('/workspace/interfaces.txt',iv['startup'][a])
                        self.assertEqual(set(iv['private_arrivals'][a]),set(BATCHES))

    def test_audit_rejects_role_instructions_even_when_asking_to_self_organize(self):
        visible,_,_=build('audit',4,'intended')
        a=next(iter(visible['startup']))
        for text in ('Choose a leader.','Please self-organize.','Delegate work.','Coordinate the other workers.'):
            modified=deepcopy(visible);modified['prompts'][a].append(text)
            self.assertFalse(audit_visible(modified)['passed'])
        modified=deepcopy(visible)
        modified['startup'][a]['/workspace/tools/new.py']='"""Choose a leader."""'
        self.assertFalse(audit_visible(modified)['passed'])

    def test_storage_preflight_refuses_without_consuming_registration(self):
        visible,_,_=build('space',4,'unintended')
        reg={'study_mode':'swarmform-structure','population':4,'harness':{'goal_mode':'off'},
             'budget':{'min_free_bytes':100}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            collection=StructureCollection(root,reg,visible,api_key='offline')
            try:
                with patch('swarmform.structure_collection.shutil.disk_usage') as usage:
                    usage.return_value.free=99
                    with self.assertRaises(RuntimeError):collection.run()
                self.assertFalse((root/'started.json').exists())
                self.assertTrue(json.loads((root/'resource-budget-stop.json').read_text())['censored'])
            finally:collection.pool.shutdown()

    def test_schedule_change_is_an_explicit_operator_factor_not_a_prompt(self):
        a,ta,ma=build('same',8,'unintended',source_schedule='fixed')
        b,tb,mb=build('same',8,'unintended',source_schedule='changing')
        self.assertEqual(a['startup'],b['startup'])
        self.assertEqual(a['prompts'],b['prompts'])
        self.assertEqual(ta['expected'],tb['expected'])
        self.assertNotEqual(ta['dependencies'],tb['dependencies'])
        self.assertEqual(digest(a),ma['worker_visible_sha256'])

    def test_legacy_population_remains_three_and_structure_requires_exact_roster(self):
        visible,_,_=build('cohort',8,'unintended')
        reg={'population':8,'harness':{'goal_mode':'off'}}
        with self.assertRaises(ValueError):Collection('/tmp/not-started',reg,visible,api_key='offline')
        reg['study_mode']='swarmform-structure'
        collection=Collection('/tmp/not-started',reg,visible,api_key='offline')
        self.assertEqual(len(collection.actors),8)
        collection.pool.shutdown()
        reg['population']=4
        with self.assertRaises(ValueError):Collection('/tmp/not-started',reg,visible,api_key='offline')


if __name__=='__main__':unittest.main()
