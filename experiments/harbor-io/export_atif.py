"""Export the current Sol Responses/bash adapter to ATIF without changing raw traces.

Other native trace formats need their own conversion and continuity validation.
"""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from harbor.models.trajectories import Trajectory

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def export_trial(folder):
 history_path=folder/'agent/history.json';history=read(history_path)
 requests=sorted((folder/'agent/trace').glob('*.request.json'))
 assert requests,'No model requests'
 first=read(requests[0]);expected=first['input'].copy();steps=[]
 def add(source,message,**kw):steps.append({'step_id':len(steps)+1,'source':source,'message':message,**kw})
 add('system',first['instructions'],extra={'native_field':'instructions'})
 for item in expected:
  role=item['role'];assert role in ('system','developer','user')
  add('system' if role=='developer' else role,item['content'],extra={'native_role':role})
 events=read(folder/'agent/events.json') if (folder/'agent/events.json').exists() else []
 by_call={e['call_id']:e for e in events};assert len(by_call)==len(events)
 used=[];source_hashes={};missing=[]
 for reqpath in requests:
  req=read(reqpath);assert req['input']==expected,'Native request history mismatch'
  assert req['instructions']==first['instructions'] and req['tools']==first['tools']
  source_hashes[str(reqpath.relative_to(folder))]=sha(reqpath)
  respath=reqpath.with_name(reqpath.name.replace('.request.json','.response.json'))
  if not respath.exists():missing.append(str(respath.relative_to(folder)));break
  res=read(respath);source_hashes[str(respath.relative_to(folder))]=sha(respath)
  calls=[v for v in res['output'] if v['type']=='function_call']
  text='\n'.join(c.get('text','') for v in res['output'] if v['type']=='message' for c in v.get('content',[]) if c.get('type')=='output_text')
  step={'model_name':res.get('model',req['model']),'reasoning_effort':req['reasoning']['effort'],'llm_call_count':1,'extra':{'native_request':str(reqpath.relative_to(folder)),'native_response':str(respath.relative_to(folder)),'native_status':res.get('status')}}
  if isinstance(res.get('created_at'),(int,float)):step['timestamp']=datetime.fromtimestamp(res['created_at'],timezone.utc).isoformat()
  usage=res.get('usage') or {}
  if usage:step['metrics']={k:v for k,v in {'prompt_tokens':usage.get('input_tokens'),'completion_tokens':usage.get('output_tokens'),'cached_tokens':(usage.get('input_tokens_details') or {}).get('cached_tokens')}.items() if v is not None}
  expected+=res['output'];observations=[]
  if calls:
   step['tool_calls']=[{'tool_call_id':c['call_id'],'function_name':c['name'],'arguments':json.loads(c['arguments'])} for c in calls]
   for c in calls:
    e=by_call.get(c['call_id'])
    if e is None:continue  # Preserve a failed/unexecuted call as such, without inventing output.
    assert c['name']=='bash' and json.loads(c['arguments'])=={'command':e['command']}
    assert e['step']==int(reqpath.name.split('.')[0])
    out=json.dumps(e['reply']);expected.append({'type':'function_call_output','call_id':c['call_id'],'output':out});used.append(c['call_id'])
    observations.append({'source_call_id':c['call_id'],'content':out})
   if observations:step['observation']={'results':observations}
  add('agent',text,**step)
 assert expected==history,'Saved final history mismatch'
 assert set(used)==set(by_call),'Unmatched tool event'
 final_path=folder/'agent/final.json'
 if final_path.exists():assert steps[-1]['message']==read(final_path)['text']
 source_hashes['agent/history.json']=sha(history_path)
 if events:source_hashes['agent/events.json']=sha(folder/'agent/events.json')
 trial_result=read(folder/'result.json')
 out={'schema_version':'ATIF-v1.8','session_id':str(trial_result['id']),'trajectory_id':str(trial_result['id'])+':primary','agent':{'name':'swarmharm-sol56','version':'1.0','model_name':first['model'],'tool_definitions':first['tools']},'steps':steps,'extra':{'conversion':'Native Responses records; developer role retained in step.extra.native_role. Opaque reasoning is retained only in raw records, not interpreted or fabricated.','source_sha256':source_hashes,'missing_response_records':missing,'verifier_result':'../result.json','business_evidence':'../verifier/business-evidence.json','provider_exception':trial_result.get('exception_info')}}
 validated=Trajectory.model_validate(out).to_json_dict();dest=folder/'agent/trajectory.json';assert not dest.exists(),'Do not replace an export'
 dest.write_text(json.dumps(validated,indent=2)+'\n')
 return {'trial':folder.name,'path':str(dest),'schema_version':'ATIF-v1.8','requests':len(requests),'tool_results':len(used),'sha256':sha(dest),'native_continuity_passed':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();assert (a.output/'completion.json').exists(),'Wait for terminal collection'
 results=[export_trial(p) for p in sorted((a.output/'trials').iterdir()) if (p/'agent/history.json').exists()]
 dest=a.output/'atif-validation.json';assert not dest.exists();dest.write_text(json.dumps({'harbor_version':'0.24.0','schema':'ATIF-v1.8','trials':results},indent=2)+'\n');print(json.dumps(results,indent=2))
