"""Export completed independent trials to validated ATIF-v1.8 trajectories."""
import argparse,hashlib,json
from pathlib import Path
from harbor.models.trajectories import Trajectory

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def export_actor(root,group,actor):
    folder=root/group/actor;history=load(folder/'history.json');requests=sorted((folder/'trace').glob('*.request.json'))
    assert requests;first=load(requests[0]);expected=first['input'].copy();steps=[];hashes={};tools=0
    def add(source,message,**kw):steps.append({'step_id':len(steps)+1,'source':source,'message':message,**kw})
    add('system',first['instructions'],extra={'native_field':'instructions'})
    for item in expected:add('system' if item['role']=='developer' else item['role'],item['content'],extra={'native_role':item['role']})
    for reqpath in requests:
        req=load(reqpath);label=reqpath.name.split('.')[0];assert req['input']==expected;hashes[str(reqpath.relative_to(folder))]=sha(reqpath);rp=reqpath.with_name(label+'.response.json')
        if not rp.exists():break
        response=load(rp);hashes[str(rp.relative_to(folder))]=sha(rp);calls=[x for x in response['output'] if x['type']=='function_call'];text='\n'.join(c.get('text','') for x in response['output'] if x['type']=='message' for c in x.get('content',[]) if c.get('type')=='output_text');expected+=response['output'];step={'model_name':response.get('model',req['model']),'reasoning_effort':req['reasoning']['effort'],'llm_call_count':1,'extra':{'native_request':str(reqpath.relative_to(folder)),'native_response':str(rp.relative_to(folder)),'native_status':response.get('status')}};observations=[]
        if calls:
            step['tool_calls']=[{'tool_call_id':c['call_id'],'function_name':c['name'],'arguments':json.loads(c['arguments'])} for c in calls]
            for i,c in enumerate(calls,1):
                tp=reqpath.with_name(label+f'-tool-{i}.json');record=load(tp);hashes[str(tp.relative_to(folder))]=sha(tp);out=json.dumps(record['result'],ensure_ascii=False);expected.append({'type':'function_call_output','call_id':c['call_id'],'output':out});observations.append({'source_call_id':c['call_id'],'content':out});tools+=1
            step['observation']={'results':observations}
        add('agent',text,**step)
    assert expected==history
    state=load(folder/'result.json');value={'schema_version':'ATIF-v1.8','session_id':group+':'+actor,'trajectory_id':group+':'+actor+':primary','agent':{'name':'SwarmHarm LessWrong business conditional collector','version':'1.0','model_name':first['model'],'tool_definitions':first['tools']},'steps':steps,'extra':{'group':group,'actor':actor,'step':state['step'],'ordinal':state['ordinal'],'native_status':state['status'],'classification':state['classification'],'source_sha256':hashes,'conversion':'Native Responses records; developer role retained in step.extra.native_role. No reasoning was fabricated.'}}
    validated=Trajectory.model_validate(value).to_json_dict();dest=folder/'agent/trajectory.json';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(validated,indent=2)+'\n');return {'actor':actor,'group':group,'path':str(dest.relative_to(root)),'sha256':sha(dest),'schema':'ATIF-v1.8','tools':tools}
def export(root):
    root=Path(root).resolve();rows=[]
    for group in ('calibration','trials'):
        folder=root/group
        if not folder.exists():continue
        for actor in sorted(p.name for p in folder.iterdir() if p.is_dir() and (p/'history.json').exists()):rows.append(export_actor(root,group,actor))
    (root/'atif-validation.json').write_text(json.dumps({'harbor_version':'0.24.0','schema':'ATIF-v1.8','trajectories':rows},indent=2)+'\n');return rows
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(export(a.output),indent=2))
