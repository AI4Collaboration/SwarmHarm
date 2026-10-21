"""Replay only frozen public bytes; no subject or provider requests."""
from pathlib import Path
from hashlib import sha256
import importlib.util,json,statistics,subprocess,time
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
spec=importlib.util.spec_from_file_location('historical_business_reader',REPO/'experiments/business-cache-v2/lab.py');lab=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab)
root=REPO/'experiments/business-cache-v2/results/2026-10-21-sol56-partial'
w=json.loads((root/'natural/world.json').read_text());shared=w['shared_files'];payload=json.dumps({p:f['data'] for p,f in shared.items()}).encode()
def normalized(v):return {'downloads':sorted(v['downloads'],key=lambda x:x['path']),'records':sorted(v['recovered_records'],key=lambda x:json.dumps(x,sort_keys=True))}
output=HERE/'evidence/2026-10-21/baseline.json';assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
value={'model_calls':0,'public_files':len(shared),'payload_bytes':len(payload),'program_sha256':sha256(lab.PUBLIC_READER.encode()).hexdigest(),'parser_runs':[],'legacy_container_runs':[],'historical_events_available':False}
for i in range(10):
 t=time.monotonic();r=subprocess.run(['python3','-I','-c',lab.PUBLIC_READER],input=payload,capture_output=True,timeout=3,check=True);value['parser_runs'].append(time.monotonic()-t);expected=normalized(json.loads(r.stdout))
for i in range(50):
 t=time.monotonic()
 try:
  data=lab.public_read(shared);assert normalized(data)==expected;row={'index':i,'passed':True,'elapsed_seconds':time.monotonic()-t}
 except Exception as e:row={'index':i,'passed':False,'error_type':type(e).__name__,'elapsed_seconds':time.monotonic()-t}
 value['legacy_container_runs'].append(row);output.write_text(json.dumps(value,indent=2)+'\n')
 if i%10==0:print(json.dumps(row),flush=True)
value['summary']={'parser_max_seconds':max(value['parser_runs']),'legacy_failures':sum(not x['passed'] for x in value['legacy_container_runs']),'legacy_max_seconds':max(x['elapsed_seconds'] for x in value['legacy_container_runs'])};output.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value['summary']),flush=True)
