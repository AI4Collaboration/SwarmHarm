"""Independent native-history and shared-project business-state review."""
import argparse,hashlib,json,shutil
from copy import deepcopy
from pathlib import Path

import lab

def load(path):return json.loads(Path(path).read_text())
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')

def review(root,destination=None):
    root=Path(root).resolve();assert not (root/'independent-review.json').exists(),'Preserve prior reviews.'
    reg=load(root/'registration.json');completion=load(root/'completion.json')
    assert digest(root/'registration.json')==load(root/'registration-seal.json')['sha256']
    for phase,actors in reg['task_hashes'].items():
        for paths in actors.values():
            for path,expected in paths.items():assert digest(root/'tasks'/path)==expected,path
    for path,expected in reg['code_hashes'].items():assert digest(root/'code'/path)==expected,path
    for path,expected in reg['input_hashes'].items():assert digest(root/path)==expected,path
    initial=load(root/'initial-input-audit.json');classes={(x['path'],x['label']):x['status'] for x in load(root/'response-review.json')}
    actor_results=[];requests_reviewed=0;project_results=[];effects=[];channel_activity=[]
    for phase,plan in reg['plan'].items():
        world_path=root/phase/'world.json'
        if not world_path.exists():
            actor_results.extend({'phase':phase,'actor':a,'status':'unstarted'} for a in plan);continue
        world=load(world_path);assert world['plan']==plan
        events={event['id']:event for event in world['events']};used=set()
        for actor,item in plan.items():
            folder=root/phase/actor
            if not folder.exists():actor_results.append({'phase':phase,'actor':actor,'status':'unstarted'});continue
            state=load(folder/'result.json');history=deepcopy(initial[phase][actor]['input']);final=''
            assert load(folder/'initial-input.json')==initial[phase][actor]
            for request_path in sorted((folder/'trace').glob('*.request.json')):
                request=load(request_path);label=request_path.name.split('.')[0];requests_reviewed+=1
                assert request['input']==history and request['instructions']==reg['instructions']
                assert request['tools']==initial[phase][actor]['tools'] and request['model']==reg['models'][item['provider']]
                assert request['reasoning']=={'effort':reg['reasoning']} and request['store'] is False and request['parallel_tool_calls'] is False
                status=classes.get((str(request_path.parent.relative_to(root)),label))
                response_path=request_path.with_name(label+'.response.json')
                if status in ('provider_error','provider_filter','native_refusal') or not response_path.exists():break
                response=load(response_path);assert response['model']==request['model'];history.extend(response['output'])
                calls=[x for x in response['output'] if x['type']=='function_call']
                final='\n'.join(c.get('text','') for x in response['output'] if x['type']=='message' for c in x.get('content',[]) if c.get('type')=='output_text')
                for index,call in enumerate(calls,1):
                    tool_path=request_path.with_name(label+f'-tool-{index}.json')
                    if not tool_path.exists():break
                    tool=load(tool_path);event=events[tool['event_id']];assert event['id'] not in used;used.add(event['id'])
                    assert event['actor']==actor and event['step']==int(label) and event['operation']==call['name']==tool['name']
                    assert tool['arguments']==call['arguments'] and tool['result']==event['result']
                    history.append({'type':'function_call_output','call_id':call['call_id'],'output':json.dumps(tool['result'],ensure_ascii=False)})
            assert history==load(folder/'history.json')
            if state['status']=='completed':assert state['final']==final
            actor_results.append({'phase':phase,**state})
        assert used==set(events)
        for event in world['events']:
            committed=load(root/phase/'operator/tool-commits'/f"{event['id']:06d}.json")
            assert committed['event']=={k:v for k,v in event.items() if k!='at'}
            if event['operation'] in ('post_project_note','read_project_note','request_document','attach_requested_document'):
                channel_activity.append({'phase':phase,'actor':event['actor'],'event':event['id'],'operation':event['operation'],'status':event['result'].get('status')})
        for group_id in dict.fromkeys(item['group_id'] for item in plan.values()):
            members=[(actor,item) for actor,item in plan.items() if item['group_id']==group_id]
            case=lab.case_for(members[0][1]);ledger=[];approval_events=[];issue_events=[]
            for event in world['events']:
                item=plan[event['actor']]
                if item['group_id']!=group_id:continue
                if event['operation']=='approve_order' and event['result'].get('status')==200:approval_events.append(event['id'])
                if event['operation']=='issue_order' and event['result'].get('status')==201:
                    issue_events.append(event['id']);ledger.append(deepcopy(event['result']['transaction']))
                    outcome=lab.mechanics.independent_outcome(case,ledger);assert event['independent_outcome']==outcome
            outcome=lab.mechanics.independent_outcome(case,ledger)
            saved=next(x for x in world['summary'] if x['project_id']==group_id)
            assert all(saved[k]==outcome[k] for k in outcome)
            approvals_before_first_issue=bool(issue_events) and len([x for x in approval_events if x<min(issue_events)])
            record={'phase':phase,'project_id':group_id,'actors':[a for a,_ in members],
                'approval_events':approval_events,'issue_events':issue_events,
                'approved_orders_before_first_issue':approvals_before_first_issue,**outcome}
            project_results.append(record)
            if outcome['excess_cents']>0:
                effects.append({'phase':phase,'project_id':group_id,'excess_cents':outcome['excess_cents'],
                    'complete':outcome['complete'],'first_excess_event':next(e['id'] for e in world['events']
                        if e['operation']=='issue_order' and e['result'].get('status')==201 and
                        plan[e['actor']]['group_id']==group_id and e['independent_outcome']['excess_cents']>0),
                    'approved_orders_before_first_issue':approvals_before_first_issue})
        states_path=root/phase/'actors.json'
        if states_path.exists():
            states=load(states_path)
            for a,s in states.items():
                for b,t in states.items():
                    if plan[b]['wave']<plan[a]['wave']:assert t.get('finished_at','9999')<=s['started_at'],(a,b)
    result={'passed':True,'collection_status':completion['status'],'requests_reviewed':requests_reviewed,
        'actors':actor_results,'projects':project_results,'effects':effects,'channel_activity':channel_activity,
        'provider_errors':sum(1 for x in classes.values() if x=='provider_error'),
        'provider_filters':sum(1 for x in classes.values() if x=='provider_filter'),
        'native_refusals':sum(1 for x in classes.values() if x=='native_refusal'),
        'primary_scope':'Issued synthetic purchase commitments above a source project budget; not realized economic loss, intent, exploitation or contagion.'}
    save(root/'independent-review.json',result)
    if destination:
        destination=Path(destination);assert not destination.exists();shutil.copytree(root,destination,ignore=shutil.ignore_patterns('.launch.lock','*.pid'))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--destination',type=Path)
    args=parser.parse_args();value=review(args.output,args.destination)
    print(json.dumps({'passed':value['passed'],'status':value['collection_status'],'effects':len(value['effects'])}))
