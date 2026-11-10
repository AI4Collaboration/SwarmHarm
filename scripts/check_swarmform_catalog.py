#!/usr/bin/env python3
"""Check existing input identity and task/network export for all five backends."""
from hashlib import sha256
import copy
import json
from pathlib import Path
import sys
import tempfile
import tomllib

ROOT=Path(__file__).resolve().parents[1];CODE=MAIN=ROOT
sys.path[:0]=[str(CODE/'experiments/runtime'),str(CODE/'experiments/swarmharm-v1'),str(CODE/'scripts')]
from swarmform.input_catalog import build,_build_workload,deployment_registration,task_network,IMPLEMENTED_ENCODINGS,business_users,observation_registration
from swarmform.domain_inputs import DOMAINS
from swarmform.inputs import digest
import run_swarmform

def business_input(visible, manifest):
    """Compare business bytes after verifying the registered IPC permission field."""
    settings=manifest['effective_settings']
    if settings['deployment']!='shared_ipc':return visible
    result=copy.deepcopy(visible)
    for files in result['startup'].values():
        config=json.loads(files['/workspace/processor.json'])
        mode=config.pop('queue_permissions',None)
        assert mode==('0620' if settings.get('request_group_write') else None)
        files['/workspace/processor.json']=json.dumps(config)+'\n'
    return result

status=json.loads((MAIN/'docs/live-rollout-status.json').read_text())
retained=[]; revised=[]
for cell,record in status['matrix']['cells'].items():
    if record['status']!='admitted':continue
    deployment,encoding,domain=cell.split('/',2)
    manifest=build('november',domain,deployment=deployment,encoding=encoding)[2]
    original=json.loads((MAIN/record['evidence']).read_text())
    if digest(manifest)==original['input_sha256']: retained.append(cell)
    else: revised.append({'cell':cell,'old':original['input_sha256'],'new':digest(manifest), 'requires_fresh_registration':True})
rows=[]
profiles=IMPLEMENTED_ENCODINGS
for kind,encodings in profiles.items():
    for domain in DOMAINS:
        baselines={}
        matched_inputs={}
        for encoding in encodings:
            visible,truth,manifest=build('november',domain,deployment=kind,encoding=encoding)
            private=build('november',domain,deployment=kind,encoding=encoding,shared=False)
            assert visible==private[0] and truth==private[1]
            variant = manifest['effective_settings'].get('workload_variant', 'baseline')
            receipt = manifest['effective_settings'].get('publication_receipt', 'package_checksum')
            query = manifest['effective_settings'].get('publication_query', 'none')
            annotations = manifest['effective_settings'].get('delivery_metadata_annotations', 'fixed_fields')
            draft_preview = manifest['effective_settings'].get('delivery_draft_preview', False)
            group_read = manifest['effective_settings'].get('published_copy_group_read', False)
            staging_read = manifest['effective_settings'].get('published_copy_staging_read', False)
            endpoint_transport = manifest['effective_settings'].get('endpoint_transport', 'tcp')
            source_appendix = manifest['effective_settings'].get('source_appendix', 'none')
            delivery_attachments = manifest['effective_settings'].get('allow_delivery_attachments', False)
            endpoint_ready_read = kind == 'worker_endpoint' and manifest['effective_settings'].get('ready_publication_read', False)
            endpoint_inventory = manifest['effective_settings'].get('local_delivery_inventory', 'none')
            release_notes = manifest['effective_settings'].get('delivery_release_notes', 'optional')
            status_notes = manifest['effective_settings'].get('public_status_notes', False)
            list_status = manifest['effective_settings'].get('delivery_list_local_status', False)
            business_visible=business_input(visible,manifest)
            matched = matched_inputs.setdefault((variant, receipt, query, annotations, draft_preview, group_read, staging_read, endpoint_transport, source_appendix, delivery_attachments, endpoint_ready_read, endpoint_inventory, release_notes, status_notes, list_status), (business_visible, truth))
            assert (business_visible, truth) == matched, ('Encoding changes a matched workload', kind, domain, encoding, variant)
            base_visible,base_truth,base_manifest = _build_workload(
                'november', domain, deployment=kind, encoding=encoding, workload_variant='baseline')
            base_input=(business_input(base_visible,base_manifest),base_truth)
            baseline = baselines.setdefault((base_manifest['effective_settings'].get('endpoint_transport','tcp'), base_manifest['effective_settings'].get('source_appendix','none'), base_manifest['effective_settings'].get('allow_delivery_attachments',False)), base_input)
            assert base_input == baseline, ('Encoding changes base workload', kind, domain, encoding)

            assert digest(manifest)!=digest(private[2])
            registered=deployment_registration(manifest)
            assert registered['kind']==kind and registered['shared'] is True
            assert deployment_registration(private[2])['shared'] is False
            policy=task_network(kind)
            assert manifest['effective_settings']['native_workstation_permissions']['networkAccess']==bool(policy['allowed_hosts'])
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                task_hashes=run_swarmform.write_tasks(root,visible,run_swarmform.IMAGE,domain,kind,manifest)
                assert len(task_hashes)==6
                assert all(run_swarmform.sha(root/path)==value for path,value in task_hashes.items())
                for actor,prompts in visible['prompts'].items():
                    task=tomllib.loads((root/'tasks'/actor/'task.toml').read_text())
                    assert task['schema_version']=='1.4'
                    assert task['agent']['user']==business_users(manifest,visible['startup'])[actor].split(':')[0]
                    assert task['environment']['network_mode']==policy['network_mode']
                    assert task['environment'].get('allowed_hosts',[])==policy['allowed_hosts']
                    assert (root/'tasks'/actor/'instruction.md').read_text()=='\n\n'.join(prompts)
            from swarmform.read_observer import MAX_ACTIVE_BYTES,MAX_TRACE_BYTES
            observation=observation_registration(manifest,visible['startup'])
            assert observation['active_trace_bytes_per_station']==MAX_ACTIVE_BYTES and observation['trace_bytes_per_log']==MAX_TRACE_BYTES
            assert observation['trace_storage']=='private_disk_volume'
            if kind in ('artifact_namespace','job_namespace'):
                from swarmform.service_capture import MAX_FILE,MAX_TOTAL
                assert observation['service_capture']==manifest['effective_settings']['service_observation_allowance']=={'max_file_bytes':MAX_FILE,'max_total_bytes':MAX_TOTAL}
            rows.append({'deployment':kind,'encoding':encoding,'domain':domain,
                'shared_private_worker_bytes_equal':True,'matched_workload_worker_bytes_equal':True,'workload_variant':variant,'publication_receipt':receipt,'publication_query':query,'delivery_metadata_annotations':annotations,'delivery_draft_preview':draft_preview,'published_copy_group_read':group_read,'published_copy_staging_read':staging_read,
                'task_export_and_native_permissions_match':True,'network':policy,'endpoint_transport':endpoint_transport,'source_appendix':source_appendix,'allow_delivery_attachments':delivery_attachments,'endpoint_ready_publication_read':endpoint_ready_read,'local_delivery_inventory':endpoint_inventory,'delivery_release_notes':release_notes,'public_status_notes':status_notes,'delivery_list_local_status':list_status,'manifest_sha256':digest(manifest)})
assert len({r['manifest_sha256'] for r in rows})==len(rows)
report={'model_calls':0,'admitted':False,'retained_input_hashes_verified':retained,'revised_inputs':revised,'input_checks':rows}
import argparse
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
if args.output:
    if args.output.exists():raise FileExistsError(args.output)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'retained_inputs':len(retained),'input_checks':len(rows),'revised_inputs':len(revised),'model_calls':0}))
