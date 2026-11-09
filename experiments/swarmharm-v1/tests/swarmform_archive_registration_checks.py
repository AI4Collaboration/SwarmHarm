"""Registration and finalization checks, without any model or Docker calls."""
import argparse, importlib.util, json, tempfile, tomllib, unittest
from pathlib import Path
from unittest.mock import patch
import export_atif
from swarmform.domain_inputs import DOMAINS, build as files
from swarmform.input_catalog import build

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('archive_entry',ROOT/'scripts/run_swarmform.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

class Checks(unittest.TestCase):
    def test_file_defaults_unchanged_and_profiles_keep_tasks_private_arrivals(self):
        for domain in DOMAINS:
            self.assertEqual(build('november',domain),files('november',domain))
            reference=None
            for encoding in ('payload_content','identifiers_metadata','operational_state'):
                a,truth,manifest=build('november',domain,deployment='artifact_namespace',encoding=encoding)
                b,other_truth,_=build('november',domain,deployment='artifact_namespace',encoding=encoding,shared=False)
                self.assertEqual(a,b);self.assertEqual(truth,other_truth)
                task=(a['prompts'],a['private_arrivals'])
                if reference is None:reference=task
                self.assertEqual(reference,task)
                self.assertTrue(manifest['effective_settings']['native_workstation_permissions']['networkAccess'])
        for args in ({'deployment':'unknown'},{'encoding':'timing'},
                     {'deployment':'artifact_namespace','encoding':'event_pattern'},{'shared':1}):
            with self.assertRaises(ValueError):build('november',**args)

    def test_paired_seals_keep_declared_network_and_effective_profile(self):
        for domain in DOMAINS:
            for deployment,encoding in (('shared_files','payload_content'),
                ('artifact_namespace','payload_content'),('artifact_namespace','identifiers_metadata'),
                ('artifact_namespace','operational_state')):
                with self.subTest(domain=domain,deployment=deployment,encoding=encoding),tempfile.TemporaryDirectory() as d:
                    root=Path(d)/'source';(root/'experiments/swarmharm-v1/registrations').mkdir(parents=True)
                    (root/'docs').mkdir();(root/'fixture.py').write_text('FROZEN = 1\n')
                    inputs,_,manifest=build('november',domain,deployment=deployment,encoding=encoding)
                    cell='/'.join((deployment,encoding,domain))
                    entry.save(root/'docs/admission.json',{'input_sha256':entry.digest(manifest)})
                    entry.save(root/'docs/live-rollout-status.json',{'maintained_registrations':[],
                        'matrix':{'cells':{cell:{'status':'admitted','evidence':'docs/admission.json'}}}})
                    args=argparse.Namespace(identifier='fixture-pair',output=Path(d)/'raw',dataset_key='november',
                        domain=domain,deployment=deployment,encoding=encoding)
                    with patch.object(entry,'ROOT',root),patch.object(entry,'published_head',return_value='fixture-source'),\
                            patch.object(entry,'check_runtime',return_value={}),patch.object(entry,'source_paths',return_value=['fixture.py']):
                        result=entry.prepare_pair(args)
                    self.assertEqual(result['model_calls'],0)
                    regs=[json.loads((args.output/m/'registration.json').read_text()) for m in ('sol56','sol61')]
                    self.assertEqual(regs[0]['matrix_cell'],cell)
                    for key in ('source_commit','input_sha256','deployment','input_hashes','task_hashes','workstation_permissions'):
                        self.assertEqual(regs[0][key],regs[1][key])
                    self.assertEqual(json.loads((args.output/'sol56/input.json').read_text()),inputs)
                    for task in (args.output/'sol56/tasks').glob('*/task.toml'):
                        environment=tomllib.loads(task.read_text())['environment']
                        self.assertEqual(environment['network_mode'],'allowlist' if deployment=='artifact_namespace' else 'no-network')
                        if deployment=='artifact_namespace':self.assertEqual(environment['allowed_hosts'],['records'])
                    seal=json.loads((args.output/'sol56/registration-seal.json').read_text())
                    self.assertEqual(seal['sha256'],entry.sha(args.output/'sol56/registration.json'))

    def test_failed_outcome_and_atif_preserve_original_files_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry.save(root/'protected-truth.json',{})
            (root/'native-record.jsonl').write_text('{"original":true}\n')
            reg={'identifier':'failed-fixture','plan':{'natural':{'actor':{'domain':'Data Analysis'}}},
                 'deployment':{'kind':'artifact_namespace'}}
            with patch.object(export_atif,'export',side_effect=ValueError('fixture validation failure')):
                result=entry.finalize_collection(root,reg,{}, {'reason':'failed','failure':'fixture'})
            self.assertEqual(result['failures'],['collection','business_outcome','atif'])
            manifest=json.loads((root/'evidence-manifest.json').read_text())
            self.assertEqual(set(manifest['files']),{'protected-truth.json','native-record.jsonl',
                'business-outcome-failure.json','atif-failure.json'})
            self.assertTrue(all(entry.sha(root/path)==sha for path,sha in manifest['files'].items()))

if __name__=='__main__':unittest.main()
