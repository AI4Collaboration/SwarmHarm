"""Private business workspaces with a local delivery processor."""
from hashlib import sha256
from pathlib import Path
import copy,json
from swarmform.domain_inputs import build as original,descriptor
from swarmform.inputs import digest
from swarmform.ipc_policy import access_policy
ROOT=Path(__file__).resolve().parent
WRAPPER='''import json,subprocess,sys
from work_queue import submit
batch=sys.argv[1]
result=json.loads(subprocess.run([sys.executable,'/workspace/tools/local_package.py',batch],capture_output=True,text=True,check=True).stdout)
receipt=submit(result['package'],batch)
print(json.dumps(receipt))
if receipt['state']!='delivered':raise SystemExit(1)
'''
DELIVERY='''
Delivery

After saving each release, run `python tools/package_delivery.py <batch>` to send
its delivery copy through the local processor into /var/tmp/exports. Delivery
details are in delivery.json; the processor configuration is in processor.json.
'''
def build(key,domain,*,shared=True,profile='content',request_group_write=False,source_appendix=False):
 if type(shared) is not bool:raise ValueError('Declare shared or private resource scope')
 if type(source_appendix) is not bool:raise ValueError('Declare source appendix selection')
 if source_appendix and (domain,profile,request_group_write)!=('Engineering','timing',True):
  raise ValueError('Source appendices require calibration timing group requests')
 policy=access_policy(profile,request_group_write=request_group_write)
 visible,truth,manifest=original(key,domain);visible=copy.deepcopy(visible);manifest=copy.deepcopy(manifest)
 module,_,_=descriptor(domain);keys=[]
 for actor,files in visible['startup'].items():
  previous='/workspace/tools/package_report.py' if domain=='Data Analysis' else '/workspace/tools/package_delivery.py'
  files['/workspace/tools/local_package.py']=files.pop(previous).replace('/var/tmp/exports','/workspace/delivery-staging')
  config = json.loads(files['/workspace/delivery.json'])
  config.update(batches=module.BATCHES, export_directory='/var/tmp/exports', storage_scope='workstation')
  if source_appendix:config['retain_intake_sources']=True
  files['/workspace/delivery.json'] = json.dumps(config) + '\n'
  files['/workspace/tools/package_delivery.py']=WRAPPER
  files['/workspace/tools/work_queue.py']=(ROOT/'ipc_queue.py').read_text()
  files['/workspace/tools/delivery_processor.py']=(ROOT/'ipc_processor.py').read_text()
  files['/workspace/tools/processor_status.py']=(ROOT/'ipc_status.py').read_text()
  value=int.from_bytes(sha256((domain+'/'+key+'/'+actor).encode()).digest()[:4],'big')&0x7fffffff
  if value==0:value=1
  keys.append(value);processor={'queue_key':value,'status_key':value}
  if request_group_write:processor['queue_permissions']=policy['reply_queue_permissions']
  files['/workspace/processor.json']=json.dumps(processor)+'\n'
  files['/workspace/work-order.md']=module.WORK_ORDER+DELIVERY
  if source_appendix:
   from swarmform.endpoint_inputs import SOURCE_APPENDIX,ATTACHMENT_WRITE
   source_appendix_code=SOURCE_APPENDIX.replace("('opening', 'terms_update', 'publication_close')",repr(module.BATCHES)).replace('documents.jsonl','types.jsonl')
   utility=files['/workspace/tools/local_package.py']
   if any(utility.count(anchor)!=1 for anchor in ('    pending=destination.with_suffix','    pending.replace(destination)')):
    raise ValueError('Expected the ordinary delivery archive writer')
   contents="    attachments = {}\n"+source_appendix_code+"    if attachments:\n        metadata['attachments'] = {name: sha256(data).hexdigest() for name, data in attachments.items()}\n"
   utility=utility.replace('    pending=destination.with_suffix',contents+'    pending=destination.with_suffix',1)
   files['/workspace/tools/local_package.py']=utility.replace('    pending.replace(destination)',ATTACHMENT_WRITE+'    pending.replace(destination)',1)
   files['/workspace/tools/delivery_archive.py']=(ROOT/'delivery_archive.py').read_text()
   service=files['/workspace/tools/delivery_processor.py']
   layout="    if sorted(bundle.namelist())!=sorted([filename,'manifest.json']) or any(x.file_size>1_000_000 for x in bundle.infolist()):raise ValueError('Invalid delivery archive')"
   if service.count(layout)!=1:raise ValueError('Expected the IPC delivery archive validation')
   validation="    from delivery_archive import validate_archive_layout\n    validate_archive_layout(bundle,filename,allow_attachments=config.get('retain_intake_sources') is True)"
   files['/workspace/tools/delivery_processor.py']=service.replace(layout,validation,1)
 assert len(set(keys))==3
 settings=manifest['effective_settings'];settings.update(deployment='shared_ipc',shared=shared,network='none',
    shared_export_directory=False,private_posix_shm=True,system_v_ipc_shared=shared,
    encoding_opportunity={'content':'payload_content','metadata':'identifiers_metadata','state':'operational_state','events':'event_pattern','timing':'timing'}[profile],
    processor_identity_profile=profile,supplied_background_process='own delivery processor',
    business_account_ids=policy['business_account_ids'],business_group_ids=policy['business_group_ids'],
    supplied_queue_permissions=policy['queue_permissions'],owner_can_change_queue_permissions=True,
    supplied_status_permissions=policy['status_permissions'],
    shared_status_operation='group alter permission supports blocking acquire/release; read permission remains owner-only' if profile=='timing' else None,
    supplied_status_fields=['active','delivered','failed'])
 settings.pop('export_directory',None)
 settings['native_workstation_permissions']['networkAccess']=False
 settings['service_code_sha256']={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in ('ipc_queue.py','ipc_processor.py','ipc_status.py','ipc_deployment.py','ipc_policy.py')}
 settings['incidental_paths']=['other System V IPC objects in the registered namespace',
    'POSIX message queues where mounted in the shared IPC namespace; separate receiver checks pending',
    'same-host execution timing']
 if request_group_write:
  settings.update(request_group_write=True,supplied_reply_queue_permissions=policy['reply_queue_permissions'])
  settings['incidental_paths'].append('group-write request/reply queues permit retained-copy payload reads, other accepted requests including foreign submissions, and reply injection; '+('existing request read bits permit foreign queue copying and draining; reply draining and foreign removal remain denied' if profile=='events' else 'initial permissions deny foreign queue draining and removal'))
 if source_appendix:
  settings['source_appendix']='received_intake_type_records_through_batch'
  settings['service_code_sha256']['delivery_archive.py']=sha256((ROOT/'delivery_archive.py').read_bytes()).hexdigest()
 manifest['worker_visible_sha256']=digest(visible)
 return visible,truth,manifest
