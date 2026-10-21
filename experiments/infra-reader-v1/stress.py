"""Replay historical public snapshots and real workstation churn, with zero models."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import argparse,statistics,tempfile,time
import reader

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
spec=importlib.util.spec_from_file_location('stress_business_v2',REPO/'experiments/business-cache-v2/lab.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
packet=REPO/'experiments/business-cache-v2/results/2026-10-21-sol56-partial'
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=HERE/'evidence/2026-10-21/stress.json');output=parser.parse_args().output;assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
def normal(v):return {'downloads':sorted(v['downloads'],key=lambda x:x['path']),'records':sorted(v['recovered_records'],key=lambda x:json.dumps(x,sort_keys=True))}
snapshots=[]
for phase in ('calibration_sol56','natural'):
 state={};world=json.loads((packet/phase/'world.json').read_text())
 for event in world['events']:
  if 'activity_file' in event:state[event['activity_file']['path']]=event['activity_file']
  for f in event.get('shared_changes',[]):
   if f.get('deleted'):state.pop(f['path'],None)
   else:state[f['path']]=f
  if 'public_reader' in event:snapshots.append((deepcopy(state),normal(event['public_reader'])))
final=deepcopy(state);expected_records=normal(world['events'][-2]['public_reader'])['records'] if 'public_reader' in world['events'][-2] else None
began=time.monotonic();rows=[];benches=[];result={'model_calls':0,'historical_snapshots':len(snapshots),'replay_cycles':10,'fresh_state_changes':100,'paused_workstations':6,'program_sha256':sha256(old.PUBLIC_READER.encode()).hexdigest(),'infra_source_sha256':sha256(Path(reader.__file__).read_bytes()).hexdigest()}
with tempfile.TemporaryDirectory(prefix='swarmharm-infra-stress-') as folder:
 engine=reader.PublicReader(old.IMAGE,old.PUBLIC_READER,Path(folder)/'reader')
 try:
  for _ in range(6):benches.append(old.Workstation({'/workspace/README.md':old.ENCODE('Offline infrastructure control.\n')}))
  for cycle in range(10):
   for state,expected in snapshots:
    t=time.monotonic();actual=engine.read(state);assert normal(actual)==expected;rows.append({'kind':'historical','seconds':time.monotonic()-t,'cache_hit':engine.last_provenance['cache_hit']})
   print(json.dumps({'cycle':cycle+1,'observations':len(rows)}),flush=True)
  for i in range(100):
   changed=deepcopy(final);changed['/registry/offline-heartbeat.json']={'data':old.ENCODE(json.dumps({'offline_counter':i}))}
   t=time.monotonic();actual=engine.read(changed);assert len({v['record']['record_id'] for v in old.disclosures(json.loads((packet/'fixtures.json').read_text()),actual)})==30
   rows.append({'kind':'new_state','seconds':time.monotonic()-t,'cache_hit':engine.last_provenance['cache_hit']})
   if i%10==0:
    for bench in benches:
     reply,snapshot=bench.execute('python -c "print(6 * 7)"',{});assert reply['exit_code']==0 and reply['stdout']=='42\n'
    print(json.dumps({'fresh_states':i+1,'workstation_commands':(i//10+1)*6}),flush=True)
  result['passed']=True
 finally:
  engine.close()
  for bench in benches:bench.close()
  events=[json.loads(line) for line in (Path(folder)/'reader/lifecycle.jsonl').read_text().splitlines()]
  result.update(observations=rows,elapsed_seconds=time.monotonic()-began,verified_cleaned_reader_containers=engine.names,
                workstations=[{'name':b.name,'closed':b.closed} for b in benches],reader_only_retries=sum(e['kind']=='reader_only_retry' for e in events),
                real_stage_timeouts=[{k:e[k] for k in ('kind','phase','container','elapsed_seconds')} for e in events if e['kind']=='stage_timeout'])
  result['summary']={'observations':len(rows),'fresh_receipts':sum(not x['cache_hit'] for x in rows),'cache_hits':sum(x['cache_hit'] for x in rows),'max_observation_seconds':max(x['seconds'] for x in rows),'model_calls':0}
  reader.atomic_json(output,result)
print(json.dumps(result['summary']),flush=True)
