"""Actual archive business witnesses, operator-only; no model calls or admission."""
import argparse,base64,json,shlex,subprocess,sys
from pathlib import Path
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'shared'),str(ROOT/'swarmform'),str(ROOT/'scripts')]
from swarmform.archive_deployment import ArtifactDeployment
from swarmform.artifact_inputs import build
from swarmform.archive_outcome import delivered_snapshots
from swarmform.domain_inputs import verify_packages
from swarmform.domain_inputs import descriptor,verify_business
from swarmform.outcomes import review
from swarmform.arrivals import IntakeSchedule
from swarmform.inputs import digest
from swarmform_witness_solvers import SOLVERS
from check_swarmform_file_deployment import RECONCILE
from swarmform.read_observer import observed_reads
SOLVERS = dict(SOLVERS, **{'Data Analysis': RECONCILE})
SOURCE_FILES = {'Engineering':'types.jsonl','Data Analysis':'postings.csv',
                'Financial Analysis':'movements.csv','Knowledge Work':'documents.jsonl'}
PUBLISH_METADATA = r'''
import sys,json,base64
from pathlib import Path
sys.path.insert(0,'/workspace/tools')
from archive_client import request
batch,filename=sys.argv[1:];data=Path('intake',batch,filename).read_bytes()
parts=[data[n:n+4096] for n in range(0,len(data),4096)]
for index,part in enumerate(parts):
 request('POST','/records',{'name':filename,'content_base64':'','metadata':{
  'kind':'source','batch':batch,'part':index,'parts':len(parts),'data':base64.b64encode(part).decode()}})
print(json.dumps({'parts':len(parts),'bytes':len(data)}))
'''
RECEIVE_METADATA = r'''
import sys,json,base64
from pathlib import Path
sys.path.insert(0,'/workspace/tools')
from archive_client import request
filename=sys.argv[1];records=request('GET','/records')['records'];groups={}
for record in records:
 m=record['metadata']
 if m.get('kind')=='source':groups.setdefault((record['author'],m['batch']),[]).append(m)
for (owner,batch),parts in groups.items():
 parts.sort(key=lambda m:m['part'])
 assert [p['part'] for p in parts]==list(range(parts[0]['parts']))
 data=b''.join(base64.b64decode(p['data'],validate=True) for p in parts)
 dest=Path('/var/tmp/exports',owner,batch,filename);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
print(json.dumps({'groups':len(groups)}))
'''
LIST_SOURCE_REFERENCES = r'''
import sys,json
sys.path.insert(0,'/workspace/tools')
from archive_client import request
records=request('GET','/records')['records']
print(json.dumps({'records':[{'id':r['id'],'author':r['author'],'metadata':{
 'kind':r['metadata']['kind'],'batch':r['metadata']['batch']}}
 for r in records if r['metadata'].get('kind')=='source']}))
'''


def exercise(domain,shared,connections,output,profile):
 module,*_=descriptor(domain);source_file=SOURCE_FILES[domain]
 inputs,truth,manifest=build(domain,'november',connections,profile,shared=shared)
 path=output/('shared' if shared else 'private')
 path.mkdir(exist_ok=False)
 (path/'input.json').write_text(json.dumps(inputs,indent=2))
 rows=[];reads=[];packages=[];terminal={}
 schedule=IntakeSchedule(inputs['private_arrivals'],manifest['effective_settings']['arrival_offsets'],activated_at=0)
 with ArtifactDeployment(inputs['startup'],shared=shared,profile=profile,observation_archive=path/'observations') as deployment:
  bindings=deployment.bindings
  for actor in module.SITES:
   snapshot=deployment.stations[actor].observe()
   assert all(base64.b64decode(snapshot['/workspace'][p])==text.encode() for p,text in inputs['startup'][actor].items())
  for stage,batch in enumerate(module.BATCHES):
   schedule.deliver_due(schedule.offsets[batch],deployment.deliver)
   for actor in module.SITES:
    metadata=json.dumps({'kind':'source','office':actor,'batch':batch})
    command=('python tools/archive_client.py upload intake/'+batch+'/'+source_file+' --metadata '+shlex.quote(metadata)) if profile=='content' else ('python -c '+shlex.quote(PUBLISH_METADATA)+' '+shlex.quote(batch)+' '+shlex.quote(source_file))
    result,_=deployment.execute(actor,command)
    assert result['exit_code']==0,result
   for actor in module.SITES:
    command='python -c '+shlex.quote(LIST_SOURCE_REFERENCES) if profile=='metadata' else 'python tools/archive_client.py list'
    result,_=deployment.execute(actor,command);assert result['exit_code']==0,result
    sources=[r for r in json.loads(result['stdout'])['records'] if r['metadata'].get('kind')=='source']
    if profile=='metadata':
     result,snapshot=deployment.execute(actor,'python -c '+shlex.quote(RECEIVE_METADATA)+' '+shlex.quote(source_file))
     assert result['exit_code']==0,result
     assert json.loads(result['stdout'])['groups']==(stage+1)*(3 if shared else 1)
     unique={(r['author'],r['metadata']['batch']):r for r in sources};sources=list(unique.values())
     for source in sources:
      if source['author']!=actor:
       denied,_=deployment.execute(actor,'python tools/archive_client.py fetch '+str(source['id'])+' /workspace/probe-body')
       assert denied['exit_code']!=0 and '403' in denied['stderr'],denied
    assert len(sources)==(stage+1)*(3 if shared else 1)
    for source in sources:
     owner=source['author'];version=source['metadata']['batch']
     dest='/var/tmp/exports/'+owner+'/'+version+'/'+source_file
     if profile=='content':
      result,snapshot=deployment.execute(actor,'python tools/archive_client.py fetch '+str(source['id'])+' '+shlex.quote(dest))
      assert result['exit_code']==0,result
     received=base64.b64decode(snapshot['/var/tmp/exports'][dest]);expected=inputs['private_arrivals'][owner][version]['intake/'+version+'/'+source_file].encode()
     assert received==expected
     reads.append({'reader':actor,'author':owner,'batch':version,'sha256':sha256(received).hexdigest(),'bytes':len(received)})
    result,snapshot=deployment.execute(actor,'python -c '+shlex.quote(SOLVERS[domain])+' '+shlex.quote(json.dumps(module.BATCHES[:stage+1])))
    assert result['exit_code']==0,result
    station=deployment.stations[actor]
    observed=observed_reads(station.previous[f'{station.command_count:06d}.log'].decode())
    for receipt in json.loads(result['stdout'])['read_files']:
     actual=b''.join(base64.b64decode(row['data_base64']) for row in observed if row['path']==receipt['path'])
     assert sha256(actual).hexdigest()==receipt['sha256'],receipt
    verified=verify_business(domain,actor,snapshot,truth,inputs)[batch]
    assert verified['complete']==shared,verified
    rows.append({'actor':actor,'batch':batch,**verified})
    result,snapshot=deployment.execute(actor,'python tools/package_delivery.py '+batch)
    assert result['exit_code']==0,result
    packed=json.loads(result['stdout']);record=packed['archive_record'];local=packed['delivery']
    packed_bytes=base64.b64decode(snapshot['/var/tmp/exports'][local['package']])
    assert record['sha256']==sha256(packed_bytes).hexdigest()
    packages.append({'actor':actor,'batch':batch,'archive_id':record['id'],'sha256':record['sha256']})
  for actor in module.SITES:
   terminal[actor]=deployment.stations[actor].observe()
   (path/(actor+'-terminal.json')).write_text(json.dumps(terminal[actor]))
 result={'status':'unadmitted_actual_deployment_witness','model_calls':0,'domain':domain,'profile':profile,'shared':shared,'input_sha256':digest(manifest),'bindings':bindings,'outcomes':rows,'received_sources':reads,'packages':packages,'resources_closed':deployment.closed,'process_reads_verified':True}
 (path/'service-terminal.json').write_text(json.dumps(deployment.terminal_service))
 final=review(domain,inputs,truth,terminal,kind='artifact_namespace',service=deployment.terminal_service)
 assert all(value==shared for value in final['business_complete'].values()),final['business_complete']
 result['independent_published_outcomes']=final['actors']
 result['publication_selection']=final['publication_selection']
 result['business_complete']=final['business_complete']
 result['private_supplements']=final['private_supplements']
 (path/'witness.json').write_text(json.dumps(result,indent=2)+'\n')
 return {'shared':shared,'correct_releases':sum(r['complete'] for r in rows),'packages':len(packages),'foreign_receipts':sum(r['reader']!=r['author'] for r in reads)}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--domain',choices=SOURCE_FILES,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--profile',choices=('content','metadata'),default='content')
 args=parser.parse_args();args.output.mkdir(exist_ok=False)
 code=args.output/'witness-code';code.mkdir()
 hashes={}
 for source in [Path(__file__),ROOT/'swarmform/scripts/swarmform_witness_solvers.py',ROOT/'swarmform/scripts/check_swarmform_file_deployment.py',*sorted((ROOT/'swarmform/swarmform').glob('*.py')),*sorted((ROOT/'shared').glob('*.py'))]:
  filename=str(source.relative_to(ROOT)); content=source.read_bytes();destination=code/filename;destination.parent.mkdir(exist_ok=True,parents=True);destination.write_bytes(content);hashes[filename]=sha256(content).hexdigest()
 (args.output/'witness-code-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
 (args.output/'runtime-source.json').write_text(json.dumps({'main_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),'source_binding':'witness-code-hashes.json','python':sys.version},indent=2)+'\n')
 # Use the exact default synthetic identities sealed by input admission.
 connections=None
 results=[exercise(args.domain,scope,connections,args.output,args.profile) for scope in (True,False)]
 left=json.loads((args.output/'shared/input.json').read_text());right=json.loads((args.output/'private/input.json').read_text());assert left==right
 (args.output/'summary.json').write_text(json.dumps({'domain':args.domain,'matched_visible_inputs':True,'results':results},indent=2)+'\n')
 print(json.dumps(results))
