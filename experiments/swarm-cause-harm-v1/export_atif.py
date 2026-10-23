"""Export Cause Harm campaign actors to validated ATIF-v1.8 trajectories."""
import argparse,hashlib,json
from pathlib import Path
from harbor.models.trajectories import Trajectory

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def export_actor(root,phase,actor):
    folder=root/phase/actor;history=read(folder/'history.json');requests=sorted((folder/'trace').glob('*.request.json'))
    assert requests,'No model requests';first=read(requests[0]);expected=first['input'].copy();steps=[];hashes={};missing=[];tools=0
    def add(source,message,**kw):steps.append({'step_id':len(steps)+1,'source':source,'message':message,**kw})
    add('system',first['instructions'],extra={'native_field':'instructions'})
    for item in expected:
        role=item['role'];assert role in ('system','developer','user')
        add('system' if role=='developer' else role,item['content'],extra={'native_role':role})
    for reqpath in requests:
        req=read(reqpath);label=reqpath.name.split('.')[0];assert req['input']==expected
        assert req['instructions']==first['instructions'] and req['tools']==first['tools']
        hashes[str(reqpath.relative_to(folder))]=sha(reqpath);respath=reqpath.with_name(label+'.response.json')
        if not respath.exists():missing.append(str(respath.relative_to(folder)));break
        response=read(respath);hashes[str(respath.relative_to(folder))]=sha(respath)
        calls=[v for v in response.get('output',[]) if v['type']=='function_call']
        text='\n'.join(c.get('text','') for v in response.get('output',[]) if v['type']=='message' for c in v.get('content',[]) if c.get('type')=='output_text')
        step={'model_name':response.get('model',req['model']),'reasoning_effort':req['reasoning']['effort'],'llm_call_count':1,'extra':{'native_request':str(reqpath.relative_to(folder)),'native_response':str(respath.relative_to(folder)),'native_status':response.get('status')}}
        usage=response.get('usage') or {}
        if usage:step['metrics']={k:v for k,v in {'prompt_tokens':usage.get('input_tokens'),'completion_tokens':usage.get('output_tokens'),'cached_tokens':(usage.get('input_tokens_details') or {}).get('cached_tokens')}.items() if v is not None}
        expected+=response.get('output',[]);observations=[]
        if calls:
            step['tool_calls']=[{'tool_call_id':c['call_id'],'function_name':c['name'],'arguments':json.loads(c['arguments'])} for c in calls]
            for index,c in enumerate(calls,1):
                tp=reqpath.with_name(label+f'-tool-{index}.json')
                if not tp.exists():continue
                record=read(tp);assert record['name']==c['name'] and record['arguments']==c['arguments']
                hashes[str(tp.relative_to(folder))]=sha(tp);out=json.dumps(record['result'],ensure_ascii=False)
                expected.append({'type':'function_call_output','call_id':c['call_id'],'output':out});tools+=1
                observations.append({'source_call_id':c['call_id'],'content':out})
            if observations:step['observation']={'results':observations}
        add('agent',text,**step)
    assert expected==history,'Saved native history mismatch'
    hashes['history.json']=sha(folder/'history.json')
    model=first['model'];state=read(folder/'result.json')
    value={'schema_version':'ATIF-v1.8','session_id':phase+':'+actor,'trajectory_id':phase+':'+actor+':primary','agent':{'name':'SwarmHarm Cause Harm collector','version':'1.0','model_name':model,'tool_definitions':first['tools']},'steps':steps,'extra':{'phase':phase,'actor':actor,'native_status':state['status'],'conversion':'Native Responses records; developer role retained in step.extra.native_role. Opaque reasoning remains only in raw records.','source_sha256':hashes,'missing_response_records':missing,'independent_review':'../../../independent-review.json'}}
    validated=Trajectory.model_validate(value).to_json_dict();dest=folder/'agent'/'trajectory.json';dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists(),'Do not replace an export';dest.write_text(json.dumps(validated,indent=2)+'\n')
    return {'phase':phase,'actor':actor,'path':str(dest.relative_to(root)),'schema_version':'ATIF-v1.8','requests':len(requests),'tool_results':tools,'sha256':sha(dest),'native_continuity_passed':True}

def export(root):
    root=Path(root).resolve();assert (root/'completion.json').exists(),'Wait for terminal collection';reg=read(root/'registration.json');results=[]
    for phase,plan in reg['plan'].items():
        for actor in plan:
            if (root/phase/actor/'history.json').exists():results.append(export_actor(root,phase,actor))
    dest=root/'atif-validation.json';assert not dest.exists(),'Do not replace an export';dest.write_text(json.dumps({'harbor_version':'0.24.0','schema':'ATIF-v1.8','trajectories':results},indent=2)+'\n');return results

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(export(a.output),indent=2))
