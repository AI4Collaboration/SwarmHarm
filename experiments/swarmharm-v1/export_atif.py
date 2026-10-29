"""Export registered Pi or Claude SDK actors to validated ATIF-v1.8 trajectories."""
import argparse,hashlib,json
from pathlib import Path
from harbor.models.trajectories import Trajectory

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text_of(content):
    if isinstance(content,str):return content
    return '\n'.join(part.get('text','') for part in content if part.get('type') in ('input_text','output_text','text'))
def arguments(raw):
    try:return json.loads(raw)
    except (TypeError,ValueError):return raw
def canonical(item):
    """The model-visible meaning of one Responses item; Pi rebuilds prior items on each request."""
    kind=item.get('type','message')
    if kind=='message':return ('message',item.get('role'),text_of(item.get('content','')))
    if kind=='function_call':return ('function_call',item['call_id'],item['name'],arguments(item['arguments']))
    if kind=='function_call_output':return ('function_call_output',item['call_id'],item['output'])
    if kind=='reasoning':return ('reasoning',item.get('encrypted_content') or item.get('id'))
    return (kind,json.dumps(item,sort_keys=True))
def system_prompt_update(expected,incoming,tools_changed):
    """Pi re-renders its system prompt, which lists the active tools, at the next run after they change."""
    if canonical(incoming[0])==canonical(expected[0]):return None
    assert tools_changed and incoming[0].get('role')==expected[0].get('role'),'Native request rewrote prior history'
    return incoming[0]
def appended_input(expected,incoming):
    head=[canonical(item) for item in incoming[:len(expected)]]
    assert head==[canonical(item) for item in expected],'Native request rewrote prior history'
    return incoming[len(expected):]

def completion_feedback_message(feedback):
    message=feedback.get('input_message')
    if message is None:return None
    assert message.get('role') in ('user','developer') and isinstance(message.get('content'),str)
    return message

def input_step(message, **extra):
    role=message.get('role');content=message.get('content')
    assert role in ('system','developer','user') and isinstance(content,str)
    return {'source':'system' if role=='developer' else role,'message':content,
        'extra':{'native_role':role,**extra}}

def claude_native_evidence(folder,requests):
    """Bind projections to SDK-native content; do not claim provider-context access."""
    native=folder/'claude'/'native';paths=sorted(native.glob('*.json'))
    assert paths,'Missing Claude SDK native evidence'
    messages={str(path.relative_to(folder/'claude')):read(path) for path in paths}
    session=read(folder/'result.json')['claude_session']['session_id']
    for message in messages.values():
        assert not message.get('session_id') or message['session_id']==session,'Claude session identity changed'
        assert message.get('type')=='tool_progress' or not message.get('parent_tool_use_id'),'Unexpected nested Claude context'
        assert message.get('subtype')!='compact_boundary','Claude context was compacted'
    for reqpath in requests:
        req=read(reqpath);start=messages[req['native_record']]
        assert start['type']=='stream_event' and start['event']['type']=='message_start'
        assert (start['event']['message']['id'],start['event']['message']['model'])==(req['sdk_message_id'],req['model'])
        respath=reqpath.with_name(reqpath.name.replace('.request.json','.response.json'))
        if not respath.exists():continue
        response=read(respath);stop=messages[response['native_record']]
        assert stop['event']['type']=='message_stop'
        selected=[message for path,message in messages.items()
                  if req['native_record']<path<response['native_record'] and message['type']=='assistant']
        blocks=[block for message in selected for block in message['message']['content']]
        assert all(message['message']['id']==response['id'] for message in selected)
        calls=[(block['id'],block['name'].split('__',2)[2],block['input']) for block in blocks if block['type']=='tool_use']
        assert calls==[(item['call_id'],item['name'],arguments(item['arguments']))
                      for item in response['output'] if item['type']=='function_call'],'Claude projection changed native tool calls'
        assert [block['text'] for block in blocks if block['type']=='text']==[
            text_of(item['content']) for item in response['output'] if item['type']=='message'],'Claude projection changed native text'
    delivery={}
    for path in sorted((folder/'trace').glob('*-tool-*.json')):
        record=read(path)
        found=[(source,block) for source,message in messages.items()
               if message['type']=='user' and isinstance(message.get('message',{}).get('content'),list)
               for block in message['message']['content']
               if block.get('type')=='tool_result' and block.get('tool_use_id')==record['call_id']]
        for _,block in found:
            assert text_of(block['content'])==json.dumps(record['result'],ensure_ascii=False),'Claude native tool result differs from controller execution'
        delivery[record['call_id']]={'sdk_delivery_verified':bool(found),
            'native_records':['claude/'+source for source,_ in found]}
    transcript=folder/'claude'/'session.jsonl'
    if transcript.exists():paths.append(transcript)
    return {str(path.relative_to(folder)):sha(path) for path in paths},delivery

def export_actor(root,phase,actor):
    folder=root/phase/actor;history=read(folder/'history.json');requests=sorted((folder/'trace').glob('[0-9][0-9][0-9][0-9].request.json'))
    assert requests,'No model requests';first=read(requests[0]);steps=[];hashes={};missing=[];uncommitted=[];tools=0
    is_claude=read(root/'registration.json').get('harness',{}).get('kind')=='claude-code'
    assert is_claude==(first.get('record_kind')=='controller_projection'),'Trace kind differs from registered harness'
    if is_claude:
        harness=read(root/'registration.json')['harness']
        if isinstance(harness['system_prompt'],dict):
            assert first.get('system_prompt_config')==harness['system_prompt'],'Claude preset differs from registration'
        native_hashes,delivery=claude_native_evidence(folder,requests);hashes.update(native_hashes)
    system=first['input'][0];assert system.get('role') in ('developer','system'),'Pi system prompt must lead the input'
    expected=[system];initial_tools=first.get('tools',[]);all_tool_definitions=initial_tools;phase2_tools_seen=False
    platform_updates={read(p)['input_message']['content']:p for p in (folder/'trace').glob('*-platform-update.json')}
    def add(source,message,**kw):steps.append({'step_id':len(steps)+1,'source':source,'message':message,**kw})
    add('system',text_of(system['content']),extra={'native_role':system['role'],'native_field':'input[0]',
        'harness':'claude-code' if is_claude else 'pi-sdk',
        'scope':('SDK system prompt preset configuration; rendered prompt text is not captured'
                 if isinstance(harness['system_prompt'],dict) else 'controller custom system prompt; SDK-internal additions unobservable')
                if is_claude else 'provider request'})
    last_agent=None;prompt_tools=[tool['name'] for tool in initial_tools]
    for reqpath in requests:
        req=read(reqpath);label=reqpath.name.split('.')[0];extension_outputs=[]
        tool_names=[tool['name'] for tool in req.get('tools',[])]
        updated=system_prompt_update(expected,req['input'],tool_names!=prompt_tools)
        if updated is not None:
            expected[0]=updated;prompt_tools=tool_names
            add('system',text_of(updated['content']),extra={'native_role':updated['role'],'native_record':str(reqpath.relative_to(folder)),'kind':'system_prompt_update','reason':'Pi re-rendered its system prompt for a changed active tool set.'})
        for item in appended_input(expected,req['input']):
            expected.append(item)
            if item.get('type')=='function_call_output':
                extension_outputs.append({'source_call_id':item['call_id'],'content':item['output']})
                continue
            assert item.get('type','message')=='message' and item.get('role') in ('user','developer','system')
            content=text_of(item['content']);source=platform_updates.get(content)
            extra={'native_role':item['role'],'native_record':str(reqpath.relative_to(folder)),
                'kind':'platform_input_update' if source else 'harness_or_extension_input'}
            if source is not None:extra['platform_record']=str(source.relative_to(folder))
            add('system' if item['role']!='user' else 'user',content,extra=extra)
        if extension_outputs:
            assert last_agent is not None,'Tool output precedes every model response'
            steps[last_agent].setdefault('observation',{'results':[]})['results'].extend(extension_outputs)
        assert tool_names[:len(initial_tools)]==[tool['name'] for tool in initial_tools]
        if len(req.get('tools',[]))>len(all_tool_definitions):
            phase2_tools_seen=True;all_tool_definitions=req['tools']
        hashes[str(reqpath.relative_to(folder))]=sha(reqpath);respath=reqpath.with_name(label+'.response.json')
        if not respath.exists():missing.append(str(respath.relative_to(folder)));break
        response=read(respath);hashes[str(respath.relative_to(folder))]=sha(respath)
        if [canonical(item) for item in history]==[canonical(item) for item in expected]:
            uncommitted.append(str(respath.relative_to(folder)))
            break
        output=response.get('output',[]);calls=[v for v in output if v['type']=='function_call']
        text='\n'.join(text_of(v.get('content',[])) for v in output if v['type']=='message')
        step={'model_name':response.get('model',req['model']),'reasoning_effort':(req.get('reasoning') or {}).get('effort'),'llm_call_count':1,'extra':{'native_request':str(reqpath.relative_to(folder)),'native_response':str(respath.relative_to(folder)),'native_status':response.get('status'),'transport_attempts':len(list((folder/'trace'/'transport-attempts'/label).glob('*.request.json')))}}
        usage=response.get('usage') or {}
        if usage:step['metrics']={k:v for k,v in {'prompt_tokens':usage.get('input_tokens'),'completion_tokens':usage.get('output_tokens'),'cached_tokens':(usage.get('input_tokens_details') or {}).get('cached_tokens')}.items() if v is not None}
        expected.extend(output);observations=[]
        if calls:
            step['tool_calls']=[{'tool_call_id':c['call_id'],'function_name':c['name'],'arguments':arguments(c['arguments'])} for c in calls]
            records={}
            for tp in sorted(reqpath.parent.glob(label+'-tool-*.json')):
                record=read(tp);records[record['call_id']]=(tp,record)
            # SDK handlers may be dispatched in a different order from content
            # blocks. Preserve the controller's actual sequential event order.
            executed_order=(sorted(calls,key=lambda c:records[c['call_id']][1]['event_id']
                if c['call_id'] in records else float('inf')) if is_claude else calls)
            for c in executed_order:
                if c['call_id'] not in records:continue
                tp,record=records[c['call_id']];assert record['name']==c['name'] and record['arguments']==c['arguments']
                hashes[str(tp.relative_to(folder))]=sha(tp);out=json.dumps(record['result'],ensure_ascii=False)
                expected.append({'type':'function_call_output','call_id':c['call_id'],'output':out});tools+=1
                observations.append({'source_call_id':c['call_id'],'content':out})
            if observations:step['observation']={'results':observations}
        add('agent',text,**step);last_agent=len(steps)-1
        completion_path=reqpath.with_name(label+'-completion-state.json')
        if completion_path.exists():hashes[str(completion_path.relative_to(folder))]=sha(completion_path)
    assert [canonical(item) for item in expected]==[canonical(item) for item in history],'Saved native history mismatch'
    hashes['history.json']=sha(folder/'history.json')
    model=first['model'];state=read(folder/'result.json')
    value={'schema_version':'ATIF-v1.8','session_id':phase+':'+actor,'trajectory_id':phase+':'+actor+':primary','agent':{'name':'SwarmHarm continuous rollout collector (Pi SDK)','version':'2.0','model_name':model,'tool_definitions':all_tool_definitions},'steps':steps,'extra':{'phase':phase,'actor':actor,'phase2_tools_seen':phase2_tools_seen,'native_status':state['status'],'completion_attempts':len(state.get('completion_attempts',[])),'extension_continuations':len(state.get('extension_continuations',[])),'harness_rejected_tool_calls':len(state.get('harness_rejected_tool_calls',[])),'pi_session_file':(state.get('pi_session') or {}).get('session_file'),'conversion':'One Pi session spans Phase 1 and Phase 2. Native records are the exact provider request payloads and completed Responses objects. Pi rebuilds prior items on each request, so continuity is checked on the model-visible meaning of each item. The Pi system prompt is the first input item. Controller platform updates and harness or extension inputs are retained as separate input steps. Observations of tools run inside Pi extensions come from the next native request. Pi re-renders its system prompt when the active tools change; each new version is retained as a system step. Opaque reasoning remains only in raw records.','source_sha256':hashes,'missing_response_records':missing,'uncommitted_response_records':uncommitted,'independent_review':'../../../independent-review.json'}}
    if is_claude:
        value['agent']['name']='SwarmHarm continuous rollout collector (Claude Agent SDK / subscription)'
        value['extra'].pop('pi_session_file')
        value['extra'].update({
            'claude_session':state['claude_session']['session_id'],
            'provider_http_payloads_captured':False,
            'provider_context_continuity_verified':False,
            'system_prompt_config':harness['system_prompt'] if isinstance(harness['system_prompt'],dict) else None,
            'goal_mode':harness['goal_mode'],
            'goal_evaluator':harness.get('goal_evaluator'),
            'goal_native_records':[str(path.relative_to(folder)) for path in sorted((folder/'claude/native').glob('*.json'))
                if (read(path).get('type')=='active_goal' or read(path).get('local_command_run',{}).get('command')=='goal')],
            'conversion':'One persistent Claude Code session spans both phases. SDK-native messages and any mirrored session transcript are retained and hashed. Request/response JSON files are controller projections checked against native SDK message IDs, text and tool calls. Continuity checks establish SDK session identity and controller history, not complete model-visible provider context. SDK-internal prompts and transport retries are not observable.',
        })
        for step in value['steps']:
            if step['source']=='agent':
                step['extra']['record_kind']='controller_projection_from_sdk_messages'
                step['extra']['tool_result_delivery']={call['tool_call_id']:delivery[call['tool_call_id']]
                    for call in step.get('tool_calls',[]) if call['tool_call_id'] in delivery}
    validated=Trajectory.model_validate(value).to_json_dict();dest=folder/'agent'/'trajectory.json';dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        Trajectory.model_validate(read(dest))
        return {'phase':phase,'actor':actor,'path':str(dest.relative_to(root)),'schema_version':'ATIF-v1.8','requests':len(requests),'tool_results':tools,'sha256':sha(dest),'native_continuity_passed':True,'preserved_existing_export':True}
    dest.write_text(json.dumps(validated,indent=2)+'\n')
    return {'phase':phase,'actor':actor,'path':str(dest.relative_to(root)),'schema_version':'ATIF-v1.8','requests':len(requests),'tool_results':tools,'sha256':sha(dest),'native_continuity_passed':True,'preserved_existing_export':False}

def export(root):
    root=Path(root).resolve();assert (root/'completion.json').exists(),'Wait for terminal collection';reg=read(root/'registration.json');results=[]
    for phase,plan in reg['plan'].items():
        for actor in plan:
            if (root/phase/actor/'history.json').exists():results.append(export_actor(root,phase,actor))
    dest=root/'atif-validation.json';assert not dest.exists(),'Do not replace an export';dest.write_text(json.dumps({'harbor_version':'0.24.0','schema':'ATIF-v1.8','trajectories':results},indent=2)+'\n');return results

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(export(a.output),indent=2))
