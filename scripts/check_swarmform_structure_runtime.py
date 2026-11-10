#!/usr/bin/env python3
"""Exercise real scalable transports and private-scope counterparts; no model calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import shlex
import sys
import time

import run_swarmform as base
from swarmform.collection import save
from swarmform.structure import build, POPULATIONS, DEPLOYMENTS
from swarmform.deployments import make_deployment
from guardrails import outside_repository


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--population',type=int,choices=POPULATIONS,required=True)
    parser.add_argument('--deployment',choices=DEPLOYMENTS,default='shared_files')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--observation-settle-seconds',type=int,choices=[2,10],default=2)
    parser.add_argument('--concurrent-rounds',type=int,choices=[0,3],default=0)
    args=parser.parse_args()
    if args.concurrent_rounds and args.deployment!='shared_files':
        parser.error('Concurrent filesystem stress is specific to shared_files')
    output=outside_repository(args.output,base.ROOT,'Witness output')
    if output.exists():raise FileExistsError('Use a new witness output directory')
    output.mkdir(parents=True)
    runtime=base.check_runtime()
    records=[];stress=[]
    for shared in (True,False):
        visible,_,manifest=build('offline-witness',args.population,'unintended',args.deployment)
        reg={'study_mode':'swarmform-structure','population':args.population,
             'observation_settle_seconds':args.observation_settle_seconds,
             'workstation_permissions':manifest['effective_settings']['native_workstation_permissions'],
             'deployment':{'kind':args.deployment,'shared':shared,'catalog_profile':'content'}}
        folder=output/('shared' if shared else 'private')
        expected={a:secrets.token_hex(24) for a in visible['startup']}
        with make_deployment(visible['startup'],reg,observation_archive=folder/'reads') as deployment:
            save(folder/'bindings.json',deployment.bindings)
            for actor,value in expected.items():
                if args.deployment=='shared_files':
                    code=f"from pathlib import Path; Path('/var/tmp/exports/{actor}.witness').write_text({value!r})"
                else:
                    code=f"import sys;sys.path.insert(0,'/workspace/tools');from archive_client import upload;from pathlib import Path;p=Path('/workspace/{actor}.witness');p.write_text({value!r});print(upload(p))"
                result,_=deployment.execute(actor,'python -c '+shlex.quote(code))
                if result['exit_code']!=0:raise RuntimeError('Witness writer failed: '+actor)
            for actor in expected:
                if args.deployment=='shared_files':
                    code="import json;from pathlib import Path;print(json.dumps({p.name[:-8]:p.read_text() for p in Path('/var/tmp/exports').glob('*.witness')}))"
                else:
                    code="import sys,json,base64;sys.path.insert(0,'/workspace/tools');from archive_client import request;data=request('GET','/records');print(json.dumps(data))"
                    # Read each actual returned record, rather than assuming the catalog envelope.
                    code="""import sys,json,base64
sys.path.insert(0,'/workspace/tools')
from archive_client import request
data=request('GET','/records')
rows=data if isinstance(data,list) else data.get('records',[])
out={}
for row in rows:
 r=request('GET','/record?id='+str(row['id']))
 out[r['name'][:-8]]=base64.b64decode(r['content_base64']).decode()
print(json.dumps(out))"""
                result,_=deployment.execute(actor,'python -c '+shlex.quote(code))
                if result['exit_code']!=0:raise RuntimeError('Witness reader failed: '+actor)
                actual=json.loads(result['stdout'])
                wanted=expected if shared else {actor:expected[actor]}
                if actual!=wanted:raise RuntimeError('Transport or isolation mismatch: '+actor)
                records.append({'shared':shared,'actor':actor,'received_actors':sorted(actual),'matched':True})
            if args.concurrent_rounds:
                # Fresh fixture-only processes exercise quiescence under concurrent I/O;
                # these scripted actions are never shown to experimental participants.
                heartbeat="import time;from pathlib import Path\nwhile True:\n Path('/workspace/witness-heartbeat').write_text(str(time.monotonic_ns()))\n time.sleep(.005)"
                for actor in expected:
                    result,_=deployment.execute(actor,'python -c '+shlex.quote(heartbeat)+' </dev/null >/tmp/witness-heartbeat.log 2>&1 &')
                    if result['exit_code']!=0:raise RuntimeError('Background witness failed')
                for round_index in range(args.concurrent_rounds):
                    started=time.monotonic();tokens={a:secrets.token_hex(32) for a in expected}
                    def write(actor):
                        code=f"from pathlib import Path;Path('/var/tmp/exports/{actor}.stress').write_text({tokens[actor]!r}*1024)"
                        result,snapshot=deployment.execute(actor,'python -c '+shlex.quote(code))
                        if result['exit_code']!=0:raise RuntimeError('Concurrent witness writer failed')
                        return snapshot.get('quiescence')
                    with ThreadPoolExecutor(max_workers=args.population) as pool:write_quiescence=list(pool.map(write,expected))
                    def read(actor):
                        # Only hashes cross the native output limit; every full payload is actually read.
                        code="import json,hashlib;from pathlib import Path;print(json.dumps({p.name[:-7]:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/var/tmp/exports').glob('*.stress')}))"
                        result,snapshot=deployment.execute(actor,'python -c '+shlex.quote(code))
                        wanted={a:base.sha256((v*1024).encode()).hexdigest() for a,v in tokens.items() if shared or a==actor}
                        if result['exit_code']!=0 or json.loads(result['stdout'])!=wanted:raise RuntimeError('Concurrent transfer/isolation mismatch')
                        return snapshot.get('quiescence')
                    with ThreadPoolExecutor(max_workers=args.population) as pool:read_quiescence=list(pool.map(read,expected))
                    observed=[x for x in write_quiescence+read_quiescence if x]
                    if args.observation_settle_seconds!=2 and len(observed)!=2*args.population:raise RuntimeError('Missing settling evidence')
                    stress.append({'shared':shared,'round':round_index+1,'actors':args.population,'payload_bytes_per_actor':65536,
                        'matched':True,'elapsed_seconds':time.monotonic()-started,'quiescence':observed})
    report={'passed':True,'population':args.population,'deployment':args.deployment,
            'observation_settle_seconds':args.observation_settle_seconds,
            'image':base.IMAGE,'runtime':runtime,'source_commit':base.git('rev-parse','HEAD'),
            'code_hashes':{p:base.sha(base.ROOT/p) for p in base.source_paths()},
            'witness_code_sha256':base.sha(Path(__file__)),
            'concurrent_rounds':args.concurrent_rounds,'concurrent_io_checks':stress,
            'model_calls':0,'scope':'Fresh payloads through real workstations; all readers, shared and private counterparts. Not behavioral evidence.',
            'checks':records}
    save(output/'witness.json',report)
    print(json.dumps({'passed':True,'path':str(output/'witness.json'),'model_calls':0}))


if __name__=='__main__':main()
