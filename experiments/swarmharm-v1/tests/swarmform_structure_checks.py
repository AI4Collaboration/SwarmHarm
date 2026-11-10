"""Construct validity, cohort scaling and role-neutral input checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import sys
import tomllib
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from swarmform.structure import (build, audit_visible, verify_solvability, POPULATIONS, BATCHES,
    build_theory, verify_theory_inputs, theory_output_inventory, THEORY_JOINT_CONTEXT,
    THEORY_START)
from swarmform.collection import Collection
from swarmform.structure_collection import StructureCollection
from swarmform.inputs import digest


class StructureChecks(unittest.TestCase):
    def test_structure_finalization_retains_coverage_after_partial_export(self):
        scripts=str(Path(__file__).resolve().parents[3]/'scripts')
        with patch.object(sys,'path',[scripts,*sys.path]):
            import run_swarmform_structure as runner
        from swarmform.collection import save
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);actors=[f'Research{i:02d}' for i in range(1,9)]
            reg={'identifier':'partial-export-fixture','workload':'navier-stokes-theory',
                 'study_mode':'swarmform-structure','population':8,
                 'plan':{'natural':dict.fromkeys(actors,{})}}
            save(root/'completion.json',{'reason':'runtime_failure'})
            save(root/'terminal-snapshots.json',{});save(root/'protected-truth.json',{})
            for actor in actors:
                save(root/'natural'/actor/'history.json',[])
                save(root/'natural'/actor/'codex/native/000001.json',{'original':True})
            def export(root,phase,actor):
                if actor=='Research04':raise AssertionError('Codex context compacted')
                return {'phase':phase,'actor':actor,'native_continuity_passed':True}
            with patch('export_atif.export_actor',side_effect=export):
                runner.finalize(root,reg,{}, {'reason':'runtime_failure','failure':{'message':'original'}})
            summary=json.loads((root/'collection-summary.json').read_text())
            self.assertEqual(summary['failures'],['collection','atif','actor_evidence'])
            coverage=json.loads((root/'actor-evidence.json').read_text())
            self.assertFalse(coverage['actor_evidence_complete'])
            self.assertEqual(coverage['missing_actors']['atif'],['Research04'])
            self.assertEqual(len(coverage['atif_actors']),7)
            files=json.loads((root/'evidence-manifest.json').read_text())['files']
            self.assertTrue({'atif-failure.json','atif-validation.json','actor-evidence.json',
                             'collection-summary.json','temporal-inventory.json'} <= set(files))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(FileExistsError):
                runner.finalize(root,reg,{}, {'reason':'quiescence'})
            self.assertEqual({p:p.read_bytes() for p in before},before)

    def test_failed_outcome_does_not_skip_temporal_inventory(self):
        scripts=str(Path(__file__).resolve().parents[3]/'scripts')
        with patch.object(sys,'path',[scripts,*sys.path]):
            import run_swarmform_structure as runner
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            reg={'identifier':'missing-outcome','plan':{'natural':{}}}
            with patch.object(runner,'time_inventory',return_value={'preserved':True}) as temporal:
                result=runner.finalize(root,reg,{}, {'reason':'runtime_failure'})
            temporal.assert_called_once_with(root,reg)
            self.assertIn('outcome',result['failures'])
            self.assertNotIn('temporal',result['failures'])
            self.assertEqual(json.loads((root/'temporal-inventory.json').read_text()),{'preserved':True})

    def test_common_problem_matches_task_and_materials_with_explicit_intended_joint_context(self):
        iv,it,im=build_theory('same',8,'intended')
        uv,ut,um=build_theory('same',8,'unintended')
        self.assertEqual(it,ut)
        self.assertNotEqual(iv['prompts'],uv['prompts'])
        self.assertEqual(iv['private_arrivals'],uv['private_arrivals'])
        self.assertTrue(verify_theory_inputs(iv,it)['passed'])
        self.assertTrue(verify_theory_inputs(uv,ut)['passed'])
        self.assertEqual(len({json.dumps(f,sort_keys=True) for f in uv['startup'].values()}),1)
        self.assertEqual(um['effective_settings']['arrival_offsets'],{'opening':0})
        self.assertFalse(um['effective_settings']['communication_wakes_models'])
        for actor in uv['startup']:
            self.assertEqual(iv['prompts'][actor][0],uv['prompts'][actor][0])
            self.assertEqual(iv['prompts'][actor][1], THEORY_JOINT_CONTEXT + THEORY_START +
                ' Read /workspace/interfaces.txt for the available messaging interface.')
            self.assertEqual(uv['prompts'][actor][1],THEORY_START)
            intended=deepcopy(iv['startup'][actor]);intended.pop('/workspace/interfaces.txt')
            intended['/workspace/environment.txt']=intended['/workspace/environment.txt'].replace(
                '\nAvailable messaging interface: /workspace/interfaces.txt.\n','')
            self.assertEqual(intended,uv['startup'][actor])
        actor=next(iter(uv['startup']))
        uv['startup'][actor]['/workspace/task.md']+='Prove a different subproblem.'
        self.assertFalse(verify_theory_inputs(uv,ut)['passed'])

    def test_joint_context_is_required_only_in_intended_and_does_not_assign_organization(self):
        intended,truth,_=build_theory('framing',8,'intended')
        unintended,other_truth,_=build_theory('framing',8,'unintended')
        self.assertIn('one of eight research agents working together',THEORY_JOINT_CONTEXT)
        self.assertTrue(audit_visible(intended)['passed'])
        changed=deepcopy(intended)
        for actor in changed['prompts']:
            changed['prompts'][actor][1]=THEORY_START
        self.assertFalse(verify_theory_inputs(changed,truth)['passed'])
        changed=deepcopy(unintended)
        for actor in changed['prompts']:
            changed['prompts'][actor][1]=THEORY_JOINT_CONTEXT+THEORY_START
        self.assertFalse(verify_theory_inputs(changed,other_truth)['passed'])

    def test_theory_input_does_not_supply_roles_or_claim_a_solution_oracle(self):
        visible,truth,_=build_theory('roles',8,'unintended')
        self.assertIsNone(truth['solution_oracle'])
        for forbidden in ('You are the reviewer.','Choose a leader.','Delegate the proof.'):
            changed=deepcopy(visible)
            changed['startup'][next(iter(changed['startup']))]['/workspace/instructions.txt']=forbidden
            self.assertFalse(verify_theory_inputs(changed,truth)['passed'])
        self.assertEqual(theory_output_inventory({})['mathematical_review'],'pending')

    def test_theory_output_readership_does_not_claim_authorship_or_correctness(self):
        import base64
        content=base64.b64encode(b'Unverified argument').decode()
        snapshots={a:{'/var/tmp/exports':{'/var/tmp/exports/navier-stokes/research.md':content}} for a in ('A','B')}
        result=theory_output_inventory(snapshots)
        self.assertEqual(len(result['versions']),1)
        self.assertEqual(result['versions'][0]['terminal_observers'],['A','B'])
        self.assertNotIn('author',result['versions'][0])
        self.assertEqual(result['mathematical_review'],'pending')

    def test_theory_metadata_names_research_and_has_no_customer_delivery_contract(self):
        scripts=str(Path(__file__).resolve().parents[3]/'scripts')
        with patch.object(sys,'path',[scripts,*sys.path]):
            import run_swarmform_structure as runner
        visible,_,manifest=build_theory('metadata',8,'intended')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            runner.write_tasks(root,visible,manifest,1200,'shared_files')
            for path in root.glob('tasks/*/task.toml'):
                task=tomllib.loads(path.read_text())
                self.assertEqual(task['task']['description'],'Navier-Stokes theoretical research')
                self.assertEqual(task['agent']['timeout_sec'],1200)

    def test_later_main_changes_do_not_replace_committed_execution_bytes(self):
        scripts=str(Path(__file__).resolve().parents[3]/'scripts')
        with patch.object(sys,'path',[scripts,*sys.path]):
            import run_swarmform_structure as runner
        with tempfile.TemporaryDirectory() as directory:
            area=Path(directory).resolve();repo=area/'repo';repo.mkdir();output=area/'evidence';output.mkdir()
            def git(*args):return subprocess.check_output(['git',*args],cwd=repo,text=True,stderr=subprocess.DEVNULL).strip()
            git('init','-q');git('config','user.name','Offline fixture');git('config','user.email','fixture@example.test')
            source=repo/'worker.py';source.write_text('original source\n')
            git('add','.');git('commit','-qm','source');commit=git('rev-parse','HEAD')
            (output/'code').mkdir();(output/'code/worker.py').write_bytes(source.read_bytes())
            (output/'input.json').write_text('{}')
            reg={'identifier':'fixture','study_mode':'swarmform-structure','source_commit':commit,
                 'code_hashes':{'worker.py':runner.base.sha(source)},
                 'input_hashes':{'input.json':runner.base.sha(output/'input.json')},'task_hashes':{},
                 'runtime':{'fixture':True},'image':runner.base.IMAGE,'harness':{}}
            folder=repo/'registrations/fixture';folder.mkdir(parents=True)
            for destination in (folder,output):
                (destination/'registration.json').write_text(json.dumps(reg))
                (destination/'registration-seal.json').write_text(json.dumps({'sha256':runner.base.sha(destination/'registration.json')}))
            source.write_text('later source\n')
            git('add','.');git('commit','-qm','registration and later source');head=git('rev-parse','HEAD')
            with patch.object(runner,'ROOT',repo),patch.object(runner.base,'ROOT',repo),patch.object(runner.base,'published_head',return_value=head),patch.object(runner.base,'check_runtime',return_value=reg['runtime']),patch.object(runner.base.codex_gateway,'verify_runtime'):
                self.assertEqual(runner.verify_registration(folder,output),reg)
                self.assertTrue(json.loads((output/'collection-preflight.json').read_text())['frozen_inputs_verified'])
                (output/'code/worker.py').write_text('later source\n')
                with self.assertRaises(ValueError):runner.verify_registration(folder,output)

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
            with patch.object(runner,'verify_registration',return_value={'study_mode':'swarmform-structure'}) as verify,patch.object(runner.subprocess,'run',side_effect=launched):
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
