from pathlib import Path
from collections import defaultdict,deque,Counter
from hashlib import sha256
import json,sys
root=Path(sys.argv[1]).resolve();destination=Path(sys.argv[2]).resolve()
def load(p):return json.loads(p.read_text())
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v):return sha256(canonical(v).encode()).hexdigest()
assert load(root/'independent-review.json')['passed']
all_records=[];surfaces=[]
for phase in ('calibration','natural'):
 path=root/phase/'world.json'
 if not path.exists():continue
 world=load(path);events=world['events'];queues=defaultdict(deque);where={}
 for e in events:queues[e['actor']].append(e)
 for actor in queues:
  traces=root/phase/actor/'trace'
  files=sorted(traces.glob('*-tool-*.json'),key=lambda p:tuple(map(int,p.stem.replace('-tool-','-').split('-'))))
  for file in files:
   record=load(file);args=json.loads(record['arguments'])
   q=queues[actor];next_event=q[0] if q else None
   if next_event and next_event['operation']==record['name'] and canonical(next_event['arguments'])==canonical(args) and canonical(next_event['result'])==canonical(record['result']):
    event=q.popleft();label=file.name.split('-')[0]
    request=file.with_name(label+'.request.json')
    response=file.with_name(label+'.response.json')
    n=int(file.stem.split('-tool-')[1]);call=[c for c in load(response)['output'] if c['type']=='function_call'][n-1]
    where[event['id']]={'request':str(request.relative_to(root)),'request_sha256':sha256(request.read_bytes()).hexdigest(),'call_id':call['call_id']}
   else:assert record['result'].get('status')==400,(str(file),next_event)
  assert not queues[actor],actor
 latest={}
 for e in events:
  if e.get('work_saved'):latest[e['arguments']['path']]=e
  if e.get('peer_work_read'):
   path=e['arguments']['path'];writer=latest[path]
   assert writer['actor']==e['peer_author'] and writer['actor']!=e['actor']
   assert canonical(writer['arguments']['content'])==canonical(e['result']['content'])
   read_context=where[e['id']];request=root/read_context['request'];input_delivery=None
   for later in sorted(request.parent.glob('*.request.json')):
    if later.name<=request.name:continue
    if any(c.get('type')=='function_call_output' and c.get('call_id')==read_context['call_id'] and canonical(json.loads(c['output']))==canonical(e['result']) for c in load(later)['input']):
     input_delivery={'request':str(later.relative_to(root)),'sha256':sha256(later.read_bytes()).hexdigest()};break
   all_records.append({'phase':phase,'reader_actor':e['actor'],'read_event':e['id'],'read_call':read_context,'first_delivery':input_delivery,'writer_actor':writer['actor'],'write_event':writer['id'],'write_call':where[writer['id']],'path':path,'body_sha256':digest(e['result']['content']),'body':e['result']['content']})
 for actor in world['state']['actors']:
  own=[e for e in events if e['actor']==actor]
  state=world['state']['actors'][actor]
  final=(root/phase/actor/'final.txt').read_text()
  surfaces.append({'phase':phase,'actor':actor,'read_records':len(state['reads']),'submissions':list(state['submissions']),'workflow_reads':[e['arguments']['path'] for e in own if e['operation']=='registry_request' and e['arguments'].get('method')=='GET' and '/ops/workflows/' in e['arguments'].get('path','')],'matching_put_attempts':[e['id'] for e in own if e['operation']=='registry_request' and e['arguments'].get('method')=='PUT' and '/ops/reviews/' in e['arguments'].get('path','')],'workflow_put_attempts':[e['id'] for e in own if e['operation']=='registry_request' and e['arguments'].get('method')=='PUT' and '/ops/workflows/' in e['arguments'].get('path','')],'payment_attempts':[{'event':e['id'],'case':e['arguments']['case_id'],'status':e['result']['status']} for e in own if e['operation']=='batch_finalize'],'final_answer':final})
result={'passed':True,'analysis':'Post-collection provenance audit; no model calls. Checks exact tool/event correspondence, true prior writer body and actual later-request delivery. Semantic adoption requires a separate reading of method content and subsequent different-invoice actions.','peer_reads':all_records,'worker_surfaces':surfaces}
for target in (root/'peer-body-provenance.json',destination/'peer-body-provenance.json'):
 assert not target.exists();target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':True,'peer_reads_by_phase':dict(Counter(r['phase'] for r in all_records)),'all_reads_delivered':all(r['first_delivery'] is not None for r in all_records),'workers':len(surfaces)}))

