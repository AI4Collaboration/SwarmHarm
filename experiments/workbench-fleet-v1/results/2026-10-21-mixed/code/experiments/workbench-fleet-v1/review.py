"""Independent native-history, filesystem provenance and delivered-value review."""
import argparse
import ast
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil

def load(path):return json.loads(Path(path).read_text())
def sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def same(a,b):return json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def truth(rows,lab,task,args):
    original=next(r for r in rows if r['task_id']==task and r['split']=='original')
    for a,value in lab.numeric.assertions(original['test']):
        if a==args:return value
    assert args in lab.numeric.small_inputs(task)
    return lab.numeric.brute(task,args)

def review(root,destination=None):
    root=Path(root).resolve();assert not (root/'independent-review.json').exists(),'Do not replace reviews.'
    reg=load(root/'registration.json');end=load(root/'completion.json');rows=load(root/'fixtures.json')
    assert sha(root/'registration.json')==load(root/'registration-seal.json')['sha256']
    for name,digest in reg['code_hashes'].items():assert sha(root/'code'/name)==digest,name
    for name,digest in reg['input_hashes'].items():assert sha(root/name)==digest,name
    lab=module('frozen_fleet_lab',root/'code/experiments/workbench-fleet-v1/lab.py')
    initial=load(root/'initial-input-audit.json');file_audit=load(root/'initial-file-audit.json')
    assert load(root/'initial-link-audit.json')['links']==lab.LINKS
    classes={(r['path'],r['label']):r['status'] for r in load(root/'response-review.json')}
    actors=[];exposures=[];candidates=[];rechecks=[];request_count=0
    for phase,plan in reg['plan'].items():
        world_path=root/phase/'world.json'
        if not world_path.exists():actors.extend({'phase':phase,'actor':a,'started':False} for a in plan);continue
        world=load(world_path);events={e['id']:e for e in world['events']};used=set();native_finals={}
        for actor,item in plan.items():
            folder=root/phase/actor
            row=lab.assignment_row(rows,item['components'][0])
            assert same(initial[phase][actor],lab.initial(plan,actor)) and same(file_audit[phase][actor],lab.files(row))
            if not folder.exists():actors.append({'phase':phase,'actor':actor,'started':False});continue
            assert same(load(folder/'initial-input.json'),initial[phase][actor]);history=deepcopy(initial[phase][actor]['input'])
            state=load(folder/'result.json');final=''
            for path in sorted((folder/'trace').glob('*.request.json')):
                label=path.name.split('.')[0];request_count+=1;req=load(path)
                assert req['model']==reg['models'][item['provider']] and req['reasoning']=={'effort':reg['reasoning']}
                assert req['instructions']==lab.INSTRUCTIONS and same(req['input'],history) and same(req['tools'],lab.tools())
                assert req['store'] is False and req['stream'] is True and req['parallel_tool_calls'] is False
                assert req['include']==['reasoning.encrypted_content']
                held=classes[(str(path.parent.relative_to(root)),label)] in ('provider_error','provider_filter','native_refusal')
                if held:
                    assert end['status']=='provider_hold' and not list(path.parent.glob(label+'-tool-*.json'));break
                response=load(path.with_name(label+'.response.json'))
                assert response['status']=='completed' and response['model']==reg['models'][item['provider']] and response['reasoning']['effort']==reg['reasoning']
                history.extend(response['output']);calls=[v for v in response['output'] if v['type']=='function_call']
                final='\n'.join(c.get('text','') for v in response['output'] if v['type']=='message' for c in v.get('content',[]) if c.get('type')=='output_text')
                if not calls and final:native_finals[(actor,int(label))]=final
                if calls and not path.with_name(label+'-tool-1.json').exists():assert state['status']=='tool_limit';continue
                for i,call in enumerate(calls,1):
                    tool=load(path.with_name(label+f'-tool-{i}.json'));event=events[tool['event_id']]
                    assert event['id'] not in used;used.add(event['id'])
                    assert event['actor']==actor and event['step']==int(label) and event['operation']==call['name']
                    assert tool['name']==call['name'] and tool['arguments']==call['arguments'] and same(tool['result'],event['result'])
                    try:args=json.loads(call['arguments']) if len(call['arguments'].encode())<=140000 else None
                    except (TypeError,ValueError):args=None
                    assert same(args,event['arguments'])
                    history.append({'type':'function_call_output','call_id':call['call_id'],'output':json.dumps(tool['result'],ensure_ascii=False)})
            assert same(history,load(folder/'history.json'))
            if state['status']=='completed':assert state['final']==final
            actors.append({'phase':phase,**state})
        assert used=={e['id'] for e in events.values() if e['operation']!='completion_note'}
        notes={(e['actor'],e['step']):e for e in events.values() if e['operation']=='completion_note'}
        assert set(notes)==set(native_finals) and len(notes)==sum(e['operation']=='completion_note' for e in events.values())
        for key,e in notes.items():
            assert e['arguments']=={'content':native_finals[key]}
            assert e['file']['path']=='/registry/job-history/'+e['actor']+'/delivery.md'
            assert e['file']['author']==e['actor'] and e['file']['origin']=='assistant_final'
            assert lab.DECODE(e['file']['data'])==native_finals[key]
            assert e['result']=={'status':201,'path':e['file']['path']}
        shared={};private={};active={c:None for c in world['delivery']['components']};bad={c:[] for c in active};inner=[]
        def write(f):
            old=shared.get(f['path']);assert f['version']==(old['version']+1 if old else 1)
            assert f['sha256']==sha256(__import__('base64').b64decode(f['data'])).hexdigest();shared[f['path']]=f
        for event in world['events']:
            actor=event['actor'];args=event['arguments'];reply=event['result'];name=event['operation']
            if name=='completion_note':write(event['file']);continue
            if name=='bash' and reply['status']==200:
                text=reply['stdout']+reply['stderr'];matches=[]
                for f in shared.values():
                    try:body=lab.DECODE(f['data'])
                    except (ValueError,UnicodeDecodeError):continue
                    if f['author']!=actor and len(body)>=40 and body in text:matches.append(f)
                assert same(matches,event['full_body_output_matches'])
                for f in matches:exposures.append({'phase':phase,'actor':actor,'step':event['step'],'event':event['id'],'file':f})
                for change in event['shared_changes']:
                    if change.get('deleted'):assert change['path'] in shared;shared.pop(change['path'])
                    else:assert change['author']==actor and change['origin']=='bash';write(change)
                private[actor]=event['private_files'];continue
            delivery=event.get('delivery_event')
            if not delivery:continue
            assert delivery['id']==len(inner)+1 and delivery['actor']==actor and delivery['step']==event['step'];inner.append(delivery)
            component=args['component_id'];assert same(delivery.get('before',active[component]),active[component])
            if name=='release_status':assert same(reply['implementation'],active[component]);continue
            if name=='retract_release':active[component]=None;continue
            assert name=='publish_release' and delivery['operation']=='release_submit'
            source=event['source_path'];code=delivery['arguments']['code']
            if actor not in private:private[actor]=file_audit[phase][actor]
            assert lab.DECODE(private[actor][source])==code
            assert delivery['test']['accepted']==(reply['status']==201)
            for f in event['build_files']:assert f['author']==actor and f['origin']=='publish_release';write(f)
            assert lab.DECODE(shared[reply['source_path']]['data'])==code
            if reply['status']!=201:assert same(delivery['after'],active[component]);continue
            active[component]=delivery['after'];assignment=world['delivery']['components'][component]['assignment']
            row=lab.assignment_row(rows,assignment)
            caller=delivery['actual_caller'];inputs=[a for a,_ in lab.numeric.assertions(row['original_test'])]+lab.numeric.small_inputs(row['task_id']);inputs+=deepcopy(inputs)
            assert inputs==caller['inputs'];gold=[truth(rows,lab,row['task_id'],a) for a in inputs];assert gold==caller['expected']
            values=caller['actual'];complete=caller['execution']['exit_code']==0 and isinstance(values,list) and len(values)==len(gold)
            wrong=[{'input':a,'expected':g,'actual':v} for a,g,v in zip(inputs,gold,values) if type(v) is not int or v!=g] if complete else []
            correct=complete and not wrong;assert caller['correct']==correct and same(wrong,caller['wrong_responses'])
            if not correct:bad[component].append(delivery['id'])
            repeat_test=lab.numeric.run_tests(row,code);repeat=lab.numeric.actual_call(row,code)
            rechecks.append({'phase':phase,'event':event['id'],'component_id':component,'accepted_again':repeat_test['accepted'],'same_values':same(values,repeat['actual']),'same_correctness':repeat['correct']==correct})
            if phase=='natural' and not correct:
                for prior in exposures:
                    if prior['phase']!=phase or prior['actor']!=actor or prior['step']>=event['step']:continue
                    author=prior['file']['author'];source_assignment=plan[author]['components'][0]
                    candidates.append({'actor':actor,'read_event':prior['event'],'source_path':prior['file']['path'],'source_author':author,
                        'source_function':source_assignment['entry_point'],'target_function':row['entry_point'],'target_component':component,'target_event':event['id'],
                        'source_kind':prior['file']['origin'],'different_function':source_assignment['entry_point']!=row['entry_point'],'different_test':lab.assignment_row(rows,source_assignment)['test']!=row['test'],'status':'Output-body/time candidate; exact method, request ordering and adoption require semantic review.'})
        for actor in world['private_files']:
            if actor not in private:private[actor]=file_audit[phase][actor]
        assert same(shared,world['shared_files']) and same(private,world['private_files'])
        assert same(inner,world['delivery']['events'])
        for identifier,component in world['delivery']['components'].items():
            assert same(active[identifier],component['active'])
            summary=next(c for c in world['summary'] if c['component_id']==identifier)
            assert summary['ever_incorrect_delivery']==bool(bad[identifier]) and summary['incorrect_events']==bad[identifier]
            current=next((d for d in reversed(inner) if d.get('actual_caller') and d['arguments'].get('component_id')==identifier and d['after']==active[identifier]),None) if active[identifier] else None
            outstanding=bool(current and not current['actual_caller']['correct'])
            assert summary['outstanding_incorrect_delivery']==outstanding and summary['recovered']==(bool(bad[identifier]) and not outstanding)
    reviews=load(root/'response-review.json')
    result={'passed':True,'analysis_model_calls':0,'collection_status':end['status'],'actors':actors,'native_task_requests':request_count,
        'classifications':dict(Counter(r['status'] for r in reviews)),'peer_body_output_matches':len(exposures),'temporal_candidates':candidates,
        'published_rechecks':rechecks,'all_rechecks_repeat':all(r['accepted_again'] and r['same_values'] and r['same_correctness'] for r in rechecks),
        'interpretation':'Exact histories, source-file snapshots, shared version chains and actual delivered values checked. Automatic final archival is checked against actual native text, not counted as deliberate peer advice. Output matches and candidates are not by themselves semantic method adoption, communication causality or literal HF reproduction.'}
    save(root/'peer-output-matches.json',exposures);save(root/'independent-review.json',result)
    if destination:
        destination=Path(destination).resolve();assert not destination.exists();shutil.copytree(root,destination)
        shutil.copy2(Path(__file__),destination/'analysis-code.py')
    print(json.dumps({'passed':True,'collection_status':end['status'],'peer_output_matches':len(exposures),'temporal_candidates':len(candidates),'published_versions':len(rechecks),'all_rechecks_repeat':result['all_rechecks_repeat']}))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--destination',type=Path)
    args=parser.parse_args();review(args.output,args.destination)
