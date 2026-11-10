"""Source sealing and independent final-package checks without hosted inference."""

import base64
import argparse
from contextlib import redirect_stderr
import importlib.util
import io
import json
import sys
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

import export_atif
from swarmform.inputs import build, verify_packages
from swarmform.input_catalog import build as build_input, task_network

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('swarmform_entry', ROOT / 'scripts/run_swarmform.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class RegistrationChecks(unittest.TestCase):
    def setUp(self):
        # Sealing checks use explicit native profiles, never a host CLI install.
        # A missed mock must fail locally as well as on a clean CI worker.
        native = patch.object(entry.codex_gateway, 'native_catalog',
                              side_effect=AssertionError('Offline checks must not query the native CLI'))
        harness = patch.object(entry.codex_gateway, 'harness_registration',
                               side_effect=lambda goal, model: {'kind': 'codex', 'goal_mode': goal})
        catalog = patch.object(entry.codex_gateway, 'gateway_catalog',
                               side_effect=lambda model, effort: {'model': model, 'effort': effort})
        for fixture in (native, harness, catalog):
            fixture.start()
            self.addCleanup(fixture.stop)

    def test_new_source_scope_preserves_runtime_dependencies_and_full_old_seals(self):
        retained = ['scripts/run_swarmform.py',
            'experiments/runtime/codex_session.py', 'experiments/runtime/codex_rpc.py',
            'experiments/runtime/codex_evidence.py', 'experiments/runtime/pi_agent.py',
            'experiments/runtime/workspace_paths.py', 'experiments/runtime/workstation_observer.py',
            'experiments/runtime/workstation_patch.py', 'experiments/runtime/Dockerfile',
            'experiments/swarmharm-v1/export_atif.py',
            'experiments/swarmharm-v1/phase2/workload_sources.py',
            'experiments/swarmharm-v1/swarmform/package_delivery.py',
            'experiments/swarmharm-v1/swarmform/archive_client.py',
            'experiments/swarmharm-v1/swarmform/job_service.py',
            'experiments/swarmharm-v1/swarmform/ipc_policy.py']
        excluded = ['scripts/check_swarmform_services.py', 'scripts/swarmform_witness_solvers.py',
            'experiments/swarmharm-v1/tests/swarmform_registration_checks.py',
            'experiments/swarmharm-v1/registrations/old/registration.json']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(entry, 'ROOT', root), \
                    patch.object(entry, 'git', return_value='\n'.join(retained + excluded)):
                self.assertEqual(entry.source_paths(), retained)

            # A historical registration can contain a now-excluded operator.
            # Its original repository AND external copy must still be checked.
            relative = excluded[0]
            registration = root / 'registration'; output = root / 'raw'
            for path in (root / relative, output / 'code' / relative):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('original operator\n')
            value = {'source_commit': 'historical', 'code_hashes': {relative: entry.sha(root / relative)},
                'input_hashes': {}, 'task_hashes': {}, 'image': entry.IMAGE, 'runtime': {}, 'harness': {}}
            for folder in (registration, output):
                entry.save(folder / 'registration.json', value)
                entry.save(folder / 'registration-seal.json', {'sha256': entry.sha(folder / 'registration.json')})
            with patch.object(entry, 'ROOT', root), patch.object(entry, 'published_head', return_value='current'), \
                    patch.object(entry, 'git', return_value='tracked'), \
                    patch.object(entry, 'source_paths', side_effect=AssertionError('Never reselect a frozen seal')), \
                    patch.object(entry, 'check_runtime', return_value={}), \
                    patch.object(entry.codex_gateway, 'verify_runtime'):
                self.assertEqual(entry.verify_frozen(registration, output), value)
                for changed in (root / relative, output / 'code' / relative):
                    with self.subTest(changed=changed):
                        changed.write_text('modified operator\n')
                        with self.assertRaisesRegex(RuntimeError, 'Source differs from frozen input'):
                            entry.verify_frozen(registration, output)
                        changed.write_text('original operator\n')

    def test_matrix_requires_all_admissions_and_prepares_selected_scope_for_selected_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source'
            (root / 'experiments/swarmharm-v1/registrations').mkdir(parents=True)
            manifests, cells = {}, {}
            for deployment, encodings in entry.IMPLEMENTED_ENCODINGS.items():
                for encoding in encodings:
                    for domain in entry.DOMAINS:
                        key = '/'.join((deployment, encoding, domain))
                        manifest = {'domain': domain, 'deployment': deployment, 'encoding': encoding}
                        manifests[(deployment, encoding, domain)] = manifest
                        number = len(cells)
                        evidence, effective = f'docs/admission-{number}.json', f'docs/input-{number}.json'
                        entry.save(root / effective, manifest)
                        entry.save(root / evidence, {'matrix_cell': key, 'status': 'admitted',
                            'input_manifest': effective, 'input_sha256': entry.digest(manifest)})
                        cells[key] = {'status': 'admitted', 'evidence': evidence}
            ledger = {'maintained_registrations': [], 'delivery_scope': {'primary_domain': 'Knowledge Work', 'generalization_domain': 'Engineering', 'generalization_encodings': list(next(iter(entry.IMPLEMENTED_ENCODINGS.values())))}, 'matrix': {'cells': cells, 'deployments': list(entry.IMPLEMENTED_ENCODINGS), 'encoding_opportunities': list(next(iter(entry.IMPLEMENTED_ENCODINGS.values()))), 'domains': list(entry.DOMAINS)}}
            missing = next(reversed(cells))
            cells[missing]['status'] = 'pending'
            entry.save(root / 'docs/live-rollout-status.json', ledger)
            args = entry.argument_parser().parse_args(['prepare-matrix', '--identifier', 'matrix-test',
                '--dataset-key', 'november', '--output', str(Path(directory) / 'raw')])
            self.assertEqual(args.model, 'openai/gpt-6.1-sol')
            runtime_value = {'fixture_runtime': True}
            prepared = []

            def fake_build(dataset_key, domain, *, deployment, encoding):
                self.assertEqual(dataset_key, 'november')
                return None, None, manifests[(deployment, encoding, domain)]

            def fake_prepare(item, source, runtime, *, profiles):
                self.assertEqual(source, 'published')
                self.assertIs(runtime, runtime_value)
                self.assertEqual(profiles[item.model][0]['goal_mode'], 'off')
                self.assertEqual(profiles[item.model][1]['effort'], 'high')
                manifest = manifests[(item.deployment, item.encoding, item.domain)]
                digest = entry.digest(manifest)
                reg = {'matrix_cell': '/'.join((item.deployment, item.encoding, item.domain)),
                    'source_commit': source, 'input_sha256': digest, 'code_hashes': {'fixture.py': 'sealed'},
                    'input_hashes': {'input.json': digest}, 'task_hashes': {'task.toml': digest},
                    'arrival_offsets': {}, 'deployment': manifest, 'budget': {},
                    'workstation_permissions': {}, 'runtime': runtime}
                entry.save(item.output / 'registration.json', reg)
                prepared.append(item)

            with patch.object(entry, 'ROOT', root), patch.object(entry, 'published_head', return_value='published') as head, \
                    patch.object(entry, 'check_runtime', return_value=runtime_value) as runtime, \
                    patch.object(entry, 'build', side_effect=fake_build), \
                    patch.object(entry, 'prepare_one', side_effect=fake_prepare) as one, \
                    patch.object(entry.codex_gateway, 'harness_registration',
                                 side_effect=lambda goal, model: {'goal_mode': goal}) as harness, \
                    patch.object(entry.codex_gateway, 'gateway_catalog',
                                 side_effect=lambda model, effort: {'model': model, 'effort': effort}) as catalog:
                result = entry.prepare_matrix(args)
                self.assertEqual(result['missing_inputs'], [missing])
                self.assertEqual(result['prepared_registrations'], 0)
                self.assertFalse(args.output.exists())
                head.assert_not_called(); runtime.assert_not_called(); one.assert_not_called()

                cells[missing]['status'] = 'admitted'
                entry.save(root / 'docs/live-rollout-status.json', ledger)
                collision = root / 'experiments/swarmharm-v1/registrations' / (
                    args.identifier + '-' + missing.lower().replace('/', '-').replace('_', '-').replace(' ', '-') + '-sol61')
                collision.mkdir()
                with self.assertRaises(FileExistsError):
                    entry.prepare_matrix(args)
                one.assert_not_called(); runtime.assert_not_called()
                self.assertFalse(args.output.exists())
                collision.rmdir()

                explicit = entry.argument_parser().parse_args(['prepare-matrix', '--identifier', 'matrix-sol56',
                    '--model', 'openai/gpt-5.6-sol', '--dataset-key', 'november',
                    '--output', str(Path(directory) / 'raw-sol56')])
                for selected in (args, explicit):
                    with self.subTest(model=selected.model):
                        for fixture in (head, runtime, one, harness, catalog):
                            fixture.reset_mock()
                        prepared.clear()
                        result = entry.prepare_matrix(selected)
                        self.assertEqual(result['prepared_inputs'], 50)
                        self.assertEqual(result['prepared_registrations'], 50)
                        self.assertEqual(result['model_calls'], 0)
                        self.assertEqual(result['model'], selected.model)
                        head.assert_called_once(); runtime.assert_called_once()
                        self.assertEqual(one.call_count, 50)
                        harness.assert_called_once_with('off', selected.model)
                        catalog.assert_called_once_with(selected.model, 'high')
                        self.assertEqual(len({item.identifier for item in prepared}), 50)
                        self.assertEqual(len({item.output for item in prepared}), 50)
                        index = json.loads(Path(result['index']).read_text())
                        self.assertEqual(index['source_commit'], 'published')
                        self.assertEqual(index['status'], 'prepared')
                        self.assertEqual(index['model'], selected.model)
                        self.assertEqual(len(index['registrations']), 50)
                        self.assertEqual(len({row['matrix_cell'] for row in index['registrations']}), 50)
                        self.assertEqual({row['model'] for row in index['registrations']}, {selected.model})
                        self.assertTrue(all(row['identifier'].endswith('-' + entry.MODEL_LABELS[selected.model])
                                            for row in index['registrations']))

    def test_matrix_rejects_unknown_model_at_argument_parsing(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            entry.argument_parser().parse_args(['prepare-matrix', '--identifier', 'matrix-test',
                '--model', 'openai/unknown', '--dataset-key', 'november', '--output', '/unused'])

    def test_pair_seals_same_published_input_and_rejects_either_reused_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source'; root.mkdir()
            (root / 'experiments/swarmharm-v1/registrations').mkdir(parents=True)
            (root / 'docs').mkdir()
            (root / 'fixture.py').write_text('VERSION = 1\n')
            _, _, manifest = build('november')
            entry.save(root / 'docs/input-admission.json', {'input_sha256': entry.digest(manifest)})
            entry.save(root / 'docs/live-rollout-status.json', {'maintained_registrations': [],
                'matrix': {'cells': {entry.CELL: {'status': 'admitted', 'evidence': 'docs/input-admission.json'}}}})
            args = argparse.Namespace(identifier='paired-test', output=Path(directory) / 'raw', dataset_key='november')
            with patch.object(entry, 'ROOT', root), patch.object(entry, 'published_head', return_value='published') as head, \
                    patch.object(entry, 'check_runtime', return_value={'harbor': '0.24.0'}) as runtime, \
                    patch.object(entry, 'source_paths', return_value=['fixture.py']):
                result = entry.prepare_pair(args)
                head.assert_called_once(); runtime.assert_called_once()
                self.assertEqual(result['model_calls'], 0)
                registrations = [json.loads((args.output / model / 'registration.json').read_text())
                                 for model in ('sol56', 'sol61')]
                self.assertEqual([r['model'] for r in registrations], ['openai/gpt-5.6-sol', 'openai/gpt-6.1-sol'])
                for key in ('source_commit', 'input_sha256', 'code_hashes', 'input_hashes', 'task_hashes'):
                    self.assertEqual(registrations[0][key], registrations[1][key])
                ledger_path = root / 'docs/live-rollout-status.json'
                ledger = ledger_path.read_bytes()
                self.assertEqual(len(json.loads(ledger)['maintained_registrations']), 2)
                for index, label in enumerate(('sol56', 'sol61')):
                    candidate = argparse.Namespace(identifier=f'collision-{index}', output=Path(directory) / f'raw-{index}',
                                                  dataset_key='november')
                    (candidate.output / label).mkdir(parents=True)
                    with self.assertRaises(FileExistsError):
                        entry.prepare_pair(candidate)
                    self.assertEqual(ledger_path.read_bytes(), ledger)
                    self.assertEqual(list(candidate.output.iterdir()), [candidate.output / label])

    def test_frozen_check_rejects_changed_input_before_native_validation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); registration = root / 'registration'; registration.mkdir()
            output = root / 'raw'; output.mkdir()
            entry.save(output / 'input.json', {'version': 1})
            value = {'source_commit': 'source', 'code_hashes': {},
                     'input_hashes': {'input.json': entry.sha(output / 'input.json')}, 'task_hashes': {}}
            for folder in (registration, output):
                entry.save(folder / 'registration.json', value)
                entry.save(folder / 'registration-seal.json', {'sha256': entry.sha(folder / 'registration.json')})
            entry.save(output / 'input.json', {'version': 2})
            with patch.object(entry, 'ROOT', root), patch.object(entry, 'published_head', return_value='current'), \
                    patch.object(entry, 'git', return_value='tracked'), \
                    patch.object(entry, 'check_runtime', side_effect=AssertionError('Too late')):
                with self.assertRaisesRegex(RuntimeError, 'Prepared input differs'):
                    entry.verify_frozen(registration, output)

    def test_package_check_does_not_treat_stale_or_different_owner_copy_as_delivery(self):
        def snapshot(office, packed_ledger, private_ledger):
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as z:
                z.writestr('ledger.csv', packed_ledger)
                z.writestr('manifest.json', json.dumps({'office': office, 'batch': 'opening',
                    'ledger_sha256': entry.sha256(packed_ledger).hexdigest()}))
            return {'/var/tmp/exports': {'/var/tmp/exports/Northline-opening.zip': base64.b64encode(data.getvalue()).decode()},
                    '/workspace': {'/workspace/releases/opening/ledger.csv': base64.b64encode(private_ledger).decode()}}
        self.assertTrue(verify_packages('Northline', snapshot('Northline', b'new', b'new'))['opening']['matches_authored_ledger'])
        self.assertFalse(verify_packages('Northline', snapshot('Northline', b'old', b'new'))['opening']['matches_authored_ledger'])
        self.assertFalse(verify_packages('Northline', snapshot('Aster', b'new', b'new'))['opening']['matches_authored_ledger'])
        self.assertFalse(verify_packages('Northline', {})['opening']['matches_authored_ledger'])

    def test_ready_publication_policy_is_explicitly_bound_to_archive_runtime(self):
        from swarmform.input_catalog import deployment_registration
        from swarmform.deployments import make_deployment
        from swarmform import archive_deployment
        cases=(('Engineering','operational_state',True),('Knowledge Work','operational_state',True),
               ('Financial Analysis','operational_state',False),('Engineering','event_pattern',True),
               ('Knowledge Work','event_pattern',True),('Financial Analysis','event_pattern',False),
               ('Knowledge Work','timing',True),('Engineering','timing',True),
               ('Financial Analysis','timing',False))
        for domain,encoding,enabled in cases:
            profile={'event_pattern':'events','operational_state':'state','timing':'timing'}[encoding]
            inputs,_,manifest=build_input('november',domain,
                deployment='artifact_namespace',encoding=encoding)
            settings=deployment_registration(manifest)
            self.assertEqual(settings.get('ready_publication_read',False),enabled)
            with patch.object(archive_deployment,'ArtifactDeployment') as factory:
                make_deployment(inputs['startup'],{'deployment':settings,
                    'workstation_permissions':{'networkAccess':True}})
                self.assertEqual(factory.call_args.kwargs['ready_publication_read'],enabled)
                self.assertEqual(factory.call_args.kwargs['profile'],profile)
            # Capture service initialization before any workstation/container starts.
            class CapturedService(Exception):pass
            captured={}
            def capture(initial,**kwargs):
                captured.update(initial)
                raise CapturedService()
            with patch.object(archive_deployment,'command'), \
                    patch.object(archive_deployment.ArtifactDeployment,'_volume',return_value='fixture-volume'), \
                    patch.object(archive_deployment,'ServiceWorkstation',side_effect=capture):
                with self.assertRaises(CapturedService):
                    archive_deployment.ArtifactDeployment(inputs['startup'],profile=profile,
                        ready_publication_read=enabled,observation_archive='/fixture-observations')
            policy=json.loads(base64.b64decode(captured['/workspace/publication-policy.json']))
            self.assertEqual(policy,{'ready_publication_read':enabled})

    def test_completed_result_policy_is_explicitly_bound_to_job_runtime(self):
        from swarmform.input_catalog import deployment_registration
        from swarmform.deployments import make_deployment
        from swarmform import job_deployment
        for domain,encoding,enabled in (('Engineering','operational_state',True),
                ('Knowledge Work','operational_state',True),('Financial Analysis','operational_state',False),
                ('Engineering','event_pattern',True),('Knowledge Work','event_pattern',True),
                ('Financial Analysis','event_pattern',False),('Engineering','timing',True),
                ('Knowledge Work','timing',True),('Financial Analysis','timing',False)):
            profile={'operational_state':'state','event_pattern':'events','timing':'timing'}[encoding]
            inputs,_,manifest=build_input('november',domain,deployment='job_namespace',encoding=encoding)
            settings=deployment_registration(manifest)
            self.assertEqual(settings.get('completed_result_read',False),enabled)
            with patch.object(job_deployment,'JobDeployment') as factory:
                make_deployment(inputs['startup'],{'deployment':settings,
                    'workstation_permissions':{'networkAccess':True}})
                self.assertEqual(factory.call_args.kwargs['completed_result_read'],enabled)
            class CapturedService(Exception):pass
            captured={}
            def capture(initial,**kwargs):
                captured.update(initial)
                raise CapturedService()
            with patch.object(job_deployment,'command'), \
                    patch.object(job_deployment.JobDeployment,'_volume',return_value='fixture-volume'), \
                    patch.object(job_deployment,'ServiceWorkstation',side_effect=capture):
                with self.assertRaises(CapturedService):
                    job_deployment.JobDeployment(inputs['startup'],profile=profile,
                        completed_result_read=enabled,observation_archive='/fixture-observations')
            policy=json.loads(base64.b64decode(captured['/workspace/publication-policy.json']))
            self.assertEqual(policy,{'completed_result_read':enabled})
        for value,profile in ((1,'state'),(True,'metadata'),(True,'content')):
            with self.assertRaisesRegex(ValueError,'registered state, event or timing profile'):
                job_deployment.JobDeployment(inputs['startup'],profile=profile,completed_result_read=value)

    def test_ipc_group_requests_bind_selected_input_to_runtime(self):
        from swarmform.input_catalog import deployment_registration
        from swarmform.deployments import make_deployment
        from swarmform import ipc_deployment
        for domain,encoding,enabled in (('Knowledge Work','identifiers_metadata',True),
                ('Engineering','identifiers_metadata',False),('Knowledge Work','payload_content',False),
                ('Knowledge Work','event_pattern',False)):
            inputs,_,manifest=build_input('november',domain,deployment='shared_ipc',encoding=encoding)
            effective=manifest['effective_settings'];registered=deployment_registration(manifest)
            self.assertEqual(registered.get('request_group_write',False),enabled)
            if enabled:
                self.assertEqual(effective['business_account_ids'],[62000,62001,62002])
                self.assertEqual(effective['business_group_ids'],[63000]*3)
                self.assertEqual(effective['supplied_queue_permissions'],'0620')
                self.assertEqual(effective['supplied_reply_queue_permissions'],'0620')
                self.assertEqual(effective['supplied_status_permissions'],'0600')
            for files in inputs['startup'].values():
                self.assertEqual(json.loads(files['/workspace/processor.json']).get('queue_permissions','0600'),
                                 '0620' if enabled else '0600')
            with patch.object(ipc_deployment,'IPCDeployment') as factory:
                make_deployment(inputs['startup'],{'deployment':registered,
                    'workstation_permissions':{'networkAccess':False}})
                self.assertEqual(factory.call_args.kwargs['request_group_write'],enabled)

    def test_ipc_group_requests_reject_invalid_or_unbound_modes_before_resources(self):
        from swarmform.ipc_inputs import build as build_ipc
        from swarmform import ipc_deployment
        inputs,_,_=build_ipc('november','Knowledge Work',profile='metadata',request_group_write=True)
        with patch.object(ipc_deployment.subprocess,'run',side_effect=AssertionError('No Docker for policy checks')):
            for value,profile in ((1,'metadata'),(None,'metadata'),('true','metadata'),
                    (True,'content'),(True,'state'),(True,'events'),(True,'timing')):
                with self.assertRaises(ValueError):
                    ipc_deployment.IPCDeployment(inputs['startup'],shared=True,
                        observation_archive='/unused',profile=profile,request_group_write=value)
            with self.assertRaisesRegex(ValueError,'permissions differ from the registration'):
                ipc_deployment.IPCDeployment(inputs['startup'],shared=True,
                    observation_archive='/unused',profile='metadata')
            own,_,_=build_ipc('november','Knowledge Work',profile='metadata')
            with self.assertRaisesRegex(ValueError,'permissions differ from the registration'):
                ipc_deployment.IPCDeployment(own['startup'],shared=True,
                    observation_archive='/unused',profile='metadata',request_group_write=True)

    def test_invalid_matrix_selectors_are_rejected(self):
        for args in ({'deployment':'unknown'},
                     {'deployment':'artifact_namespace','encoding':'unknown'},{'shared':1}):
            with self.assertRaises(ValueError):build_input('november',**args)

    def test_paired_seals_keep_declared_network_and_effective_profile(self):
        # The catalog gate covers all 100 input combinations. Exercise sealing
        # once per backend, spanning every domain and encoding, here.
        cases=(('Engineering','shared_files','payload_content'),
               ('Data Analysis','shared_ipc','identifiers_metadata'),
               ('Financial Analysis','worker_endpoint','operational_state'),
               ('Knowledge Work','artifact_namespace','event_pattern'),
               ('Data Analysis','job_namespace','timing'))
        for domain,deployment,encoding in cases:
            with self.subTest(domain=domain,deployment=deployment,encoding=encoding),tempfile.TemporaryDirectory() as d:
                root=Path(d)/'source';(root/'experiments/swarmharm-v1/registrations').mkdir(parents=True)
                (root/'docs').mkdir();(root/'fixture.py').write_text('FROZEN = 1\n')
                inputs,_,manifest=build_input('november',domain,deployment=deployment,encoding=encoding)
                cell='/'.join((deployment,encoding,domain))
                entry.save(root/'docs/admission.json',{'input_sha256':entry.digest(manifest)})
                entry.save(root/'docs/live-rollout-status.json',{'maintained_registrations':[],
                    'matrix':{'cells':{cell:{'status':'admitted','evidence':'docs/admission.json'}}}})
                args=entry.argument_parser().parse_args(['prepare-pair','--identifier','fixture-pair',
                    '--output',str(Path(d)/'raw'),'--dataset-key','november',
                    '--domain',domain,'--deployment',deployment,'--encoding',encoding])
                with patch.object(entry,'ROOT',root),patch.object(entry,'published_head',return_value='fixture-source'),\
                        patch.object(entry,'check_runtime',return_value={}),patch.object(entry,'source_paths',return_value=['fixture.py']):
                    result=entry.prepare_pair(args)
                self.assertEqual(result['model_calls'],0)
                regs=[json.loads((args.output/m/'registration.json').read_text()) for m in ('sol56','sol61')]
                for record in regs:
                    self.assertEqual(record['matrix_cell'],cell)
                    self.assertEqual(record['arrival_offsets'],manifest['effective_settings']['arrival_offsets'])
                    self.assertEqual({p['domain'] for p in record['plan']['natural'].values()},{domain})
                for key in ('source_commit','input_sha256','deployment','input_hashes','task_hashes','workstation_permissions'):
                    self.assertEqual(regs[0][key],regs[1][key])
                self.assertEqual(json.loads((args.output/'sol56/input.json').read_text()),inputs)
                for task in (args.output/'sol56/tasks').glob('*/task.toml'):
                    task_config=tomllib.loads(task.read_text())
                    self.assertEqual(task_config['agent']['timeout_sec'],regs[0]['budget']['max_agent_seconds'])
                    environment=task_config['environment']
                    expected=task_network(deployment)
                    self.assertEqual(environment['network_mode'],expected['network_mode'])
                    self.assertEqual(environment.get('allowed_hosts',[]),expected['allowed_hosts'])
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
            self.assertEqual(result['failures'],['collection','business_outcome','atif','actor_evidence'])
            self.assertFalse(result['actor_evidence_complete'])
            manifest=json.loads((root/'evidence-manifest.json').read_text())
            self.assertEqual(set(manifest['files']),{'protected-truth.json','native-record.jsonl',
                'business-outcome-failure.json','atif-failure.json','actor-evidence.json'})
            self.assertTrue(all(entry.sha(root/path)==sha for path,sha in manifest['files'].items()))


if __name__ == '__main__':
    unittest.main()
