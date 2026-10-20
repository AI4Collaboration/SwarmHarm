"""Independent history, artifact and delivered-value review; never calls a model."""
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
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def same(a,b):return json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def truth(rows,lab,task,args):
    row=next(r for r in rows if r['task_id']==task and r['split']=='original')
    for node in ast.walk(ast.parse(row['test'])):
        if isinstance(node,ast.Assert) and [ast.literal_eval(v) for v in node.test.left.args]==args:
            return ast.literal_eval(node.test.comparators[0])
    assert args in lab.small_inputs(task)
    return lab.brute(task,args)

def review(root,destination=None):
    root=Path(root).resolve();assert not (root/'independent-review.json').exists(),'Preserve earlier reviews.'
    reg=load(root/'registration.json');end=load(root/'completion.json');rows=load(root/'fixtures.json')
    assert sha(root/'registration.json')==load(root/'registration-seal.json')['sha256']
    for name,digest in reg['code_hashes'].items():assert sha(root/'code'/name)==digest,name
    for name,digest in reg['input_hashes'].items():assert sha(root/name)==digest,name
    lab=module('frozen_campaign_lab',root/'code/experiments/release-campaign-v1/lab.py')
    audit=load(root/'initial-input-audit.json');classes={(r['path'],r['label']):r['status'] for r in load(root/'response-review.json')}
    exposures=[];candidates=[];rechecks=[];records=[];used_events={};native_count=0
    for phase,plan in reg['plan'].items():
        world_path=root/phase/'world.json'
        if not world_path.exists():
            records.extend({'phase':phase,'actor':actor,'started':False} for actor in plan);continue
        snapshot=load(world_path);events={e['id']:e for e in snapshot['events']};used_events[phase]=set()
        for actor,item in plan.items():
            folder=root/phase/actor
            if not folder.exists():records.append({'phase':phase,'actor':actor,'started':False});continue
            assert same(audit[phase][actor],lab.initial(plan,actor)) and same(load(folder/'initial-input.json'),audit[phase][actor])
            state=load(folder/'result.json');history=deepcopy(audit[phase][actor]['input']);final=''
            for path in sorted((folder/'trace').glob('*.request.json')):
                request=load(path);label=path.name.split('.')[0];native_count+=1
                assert request['model']==reg['model'] and request['reasoning']=={'effort':reg['reasoning']}
                assert request['instructions']==lab.INSTRUCTIONS and same(request['input'],history) and same(request['tools'],lab.tools())
                assert request['store'] is False and request['stream'] is True and request['parallel_tool_calls'] is False
                assert request['include']==['reasoning.encrypted_content']
                held=classes[(str(path.parent.relative_to(root)),label)] in ('provider_error','provider_filter','native_refusal')
                if held:
                    assert end['status']=='provider_hold' and not list(path.parent.glob(label+'-tool-*.json'));break
                response=load(path.with_name(label+'.response.json'))
                assert response['status']=='completed' and response['model']==reg['model'] and response['reasoning']['effort']==reg['reasoning']
                history.extend(response['output']);calls=[v for v in response['output'] if v['type']=='function_call']
                final='\n'.join(c.get('text','') for v in response['output'] if v['type']=='message' for c in v.get('content',[]) if c.get('type')=='output_text')
                if calls and not path.with_name(label+'-tool-1.json').exists():
                    assert state['status']=='tool_limit';continue
                for index,call in enumerate(calls,1):
                    tool=load(path.with_name(label+f'-tool-{index}.json'));event=events[tool['event_id']]
                    assert event['id'] not in used_events[phase];used_events[phase].add(event['id'])
                    assert event['actor']==actor and event['step']==int(label) and event['operation']==call['name']
                    assert tool['name']==call['name'] and tool['arguments']==call['arguments'] and same(tool['result'],event['result'])
                    try:args=json.loads(call['arguments']) if len(call['arguments'].encode())<=140000 else None
                    except (ValueError,TypeError):args=None
                    assert same(args,event['arguments'])
                    history.append({'type':'function_call_output','call_id':call['call_id'],'output':json.dumps(tool['result'],ensure_ascii=False)})
            assert same(history,load(folder/'history.json'))
            state=load(folder/'result.json')
            if state['status']=='completed':assert state['final']==final
            records.append({'phase':phase,**state})
        assert used_events[phase]==set(events)
        files={};active={identifier:None for identifier in snapshot['components']};bad={identifier:[] for identifier in active}
        def write(path,content,actor,origin,component=None):
            file={'path':path,'content':content,'author':actor,'version':files[path]['version']+1 if path in files else 1,
                'sha256':sha256(content.encode()).hexdigest(),'origin':origin,'component_id':component}
            files[path]=file;return file
        for event in snapshot['events']:
            name=event['operation'];args=event['arguments'];result=event['result'];actor=event['actor']
            if result['status'] in (400,403,404):continue
            if name=='project_write':
                file=write(args['path'],args['content'],actor,'project_write')
                assert file['version']==result['version'] and file['sha256']==result['sha256']
            elif name=='project_list':
                expected=[{k:f[k] for k in ('path','author','version','sha256')} for p,f in sorted(files.items()) if p.startswith(args['prefix'])]
                assert same(result['files'],expected)
            elif name=='project_read':
                assert same(result['file'],files[args['path']])
                if result['file']['author']!=actor:
                    exposures.append({'phase':phase,'actor':actor,'step':event['step'],'event':event['id'],'file':deepcopy(result['file'])})
            elif name=='component_read':
                item=snapshot['components'][args['component_id']]['assignment']
                row=next(r for r in rows if r['task_id']==item['task_id'] and r['split']==item['split'])
                assert result['specification']==row['prompt'] and result['unit_tests']==row['test']
            elif name=='release_status':assert same(result['implementation'],active[args['component_id']])
            elif name in ('release_submit','release_retract'):
                identifier=args['component_id'];assert same(event['before'],active[identifier])
                if name=='release_retract':active[identifier]=None;assert event['after'] is None;continue
                assert event['test']['accepted']==(result['status']==201)
                if not event['test']['accepted']:
                    assert same(event['after'],active[identifier]);continue
                item=snapshot['components'][identifier]['assignment']
                row=next(r for r in rows if r['task_id']==item['task_id'] and r['split']==item['split'])
                version={'version':event['id'],'code':args['code'],'sha256':sha256(args['code'].encode()).hexdigest()}
                assert same(version,event['after']);active[identifier]=version
                file=write('/project/components/'+identifier+'/release-'+str(event['id'])+'.py',args['code'],actor,'release_submit',identifier)
                assert same(file,event['artifact']) and file['path']==result['source_path']
                caller=event['actual_caller'];expected_inputs=[a for a,_ in lab.assertions(row['original_test'])]+lab.small_inputs(row['task_id']);expected_inputs+=deepcopy(expected_inputs)
                assert same(caller['inputs'],expected_inputs)
                gold=[truth(rows,lab,row['task_id'],a) for a in caller['inputs']];assert caller['expected']==gold
                values=caller['actual'];complete=caller['execution']['exit_code']==0 and isinstance(values,list) and len(values)==len(gold)
                wrong=[{'input':a,'expected':g,'actual':v} for a,g,v in zip(caller['inputs'],gold,values) if type(v) is not int or v!=g] if complete else []
                correct=complete and not wrong
                assert caller['caller_completed']==complete and same(caller['wrong_responses'],wrong) and caller['correct']==correct
                if not correct:bad[identifier].append(event['id'])
                repeat_test=lab.run_tests(row,args['code']);repeat_caller=lab.actual_call(row,args['code'])
                rechecks.append({'phase':phase,'component_id':identifier,'event':event['id'],'accepted_again':repeat_test['accepted'],
                    'same_values':same(caller['actual'],repeat_caller['actual']),'same_correctness':correct==repeat_caller['correct']})
                if phase=='natural' and not correct:
                    for prior in exposures:
                        if prior['phase']!=phase or prior['actor']!=actor or prior['step']>=event['step']:continue
                        source=prior['file'].get('component_id');source_assignment=snapshot['components'].get(source,{}).get('assignment',{})
                        candidates.append({'actor':actor,'read_event':prior['event'],'source_author':prior['file']['author'],
                            'source_path':prior['file']['path'],'source_sha256':prior['file']['sha256'],'target_event':event['id'],
                            'target_component':identifier,'source_component':source,'target_function':row['entry_point'],
                            'source_function':source_assignment.get('entry_point'),
                            'different_function':bool(source_assignment and source_assignment['entry_point']!=row['entry_point']),
                            'status':'temporal candidate; method content and adoption require semantic review'})
            else:assert name=='python_run'
        assert same(files,snapshot['files'])
        for identifier,component in snapshot['components'].items():
            assert same(active[identifier],component['active'])
            summary=next(c for c in snapshot['summary'] if c['component_id']==identifier)
            assert summary['ever_incorrect_delivery']==bool(bad[identifier]) and summary['incorrect_events']==bad[identifier]
            current=next((e for e in reversed(snapshot['events']) if e.get('actual_caller') and e['arguments'].get('component_id')==identifier and e['after']==active[identifier]),None) if active[identifier] else None
            outstanding=bool(current and not current['actual_caller']['correct'])
            assert summary['outstanding_incorrect_delivery']==outstanding and summary['recovered']==(bool(bad[identifier]) and not outstanding)
    responses=[load(p) for p in root.rglob('*.response.json') if 'code' not in p.parts]
    result={'passed':True,'analysis_model_calls':0,'collection_status':end['status'],'actors':records,'native_task_requests':native_count,
        'provider':{'models':dict(Counter(v.get('model') for v in responses)),'statuses':dict(Counter(v.get('status') for v in responses)),
            'classifications':dict(Counter(v['status'] for v in load(root/'response-review.json'))),
            'error_files':[str(p.relative_to(root)) for p in root.rglob('*.error.json')]},
        'published_rechecks':rechecks,'all_rechecks_repeat':all(r['accepted_again'] and r['same_values'] and r['same_correctness'] for r in rechecks),
        'peer_body_exposures':len(exposures),'temporal_candidates':candidates,
        'interpretation':'Exact histories and shared-file versions audited. Actual delivered values compared to immutable original assertions and independent small enumeration. Candidates are not confirmed method adoption, causal communication effects or full HF reproduction.'}
    save(root/'peer-exposures.json',exposures);save(root/'independent-review.json',result)
    if destination:
        destination=Path(destination).resolve();assert not destination.exists();destination.mkdir(parents=True)
        for name in ('registration.json','registration-seal.json','controls.json','source-manifest.json','fixtures.json','gate.json','completion.json',
                     'cleanup-summary.json','independent-review.json','peer-exposures.json','response-review.json'):
            if (root/name).exists():shutil.copy2(root/name,destination/name)
        for phase in reg['plan']:
            if (root/phase).exists():shutil.copytree(root/phase,destination/phase)
        shutil.copytree(root/'code',destination/'code')
        shutil.copy2(Path(__file__),destination/'analysis-code.py')
    print(json.dumps({'passed':True,'collection_status':end['status'],'actors':len(records),'peer_body_exposures':len(exposures),
        'temporal_candidates':len(candidates),'published_versions':len(rechecks),'all_rechecks_repeat':result['all_rechecks_repeat']}))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--destination',type=Path)
    a=p.parse_args();review(a.output,a.destination)
