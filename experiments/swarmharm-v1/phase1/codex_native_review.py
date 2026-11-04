"""Bind Phase1 carrier judgments to the native Codex stream and rendered results."""
from hashlib import sha256
import json
from pathlib import Path
from phase1 import lab
codex_evidence = lab.module("phase1_codex_evidence", lab.REPO/"experiments/runtime/codex_evidence.py")


def actor_evidence(root, actor, *, sealed):
    root=Path(root).resolve();folder=root/'natural'/actor
    requests=sorted((folder/'trace').glob('*.request.json'))
    records,delivery=codex_evidence.native_evidence(folder,requests)
    if sealed:
        manifest=json.loads((root/'evidence-manifest.json').read_text())['files']
        for relative,digest in records.items():
            assert manifest.get(str((folder/relative).relative_to(root)))==digest, 'Unsealed Codex native evidence'
    return {'native_files':records,'tool_delivery':delivery,
            'evidence_scope':'Native app-server records and exact rendered tool delivery; complete provider context is not observable'}


def response(root, registration, actor, step, *, sealed):
    from phase1.carrier_trace_review import read_file,require
    root=Path(root).resolve();folder=root/'natural'/actor
    request,_=read_file(root,folder/'trace'/f'{step:04d}.request.json',sealed)
    projected,_=read_file(root,folder/'trace'/f'{step:04d}.response.json',sealed)
    require(request.get('projection_source')==projected.get('projection_source')=='codex-app-server', 'Missing native Codex projection source')
    require(request['session_id']==projected['session_id'] and request['native_turn_id']==projected['native_turn_id'], 'Codex session or turn differs')
    items=[];refs=[]
    for relative in projected['native_output_records']:
        require(request['native_record']<=relative<=projected['native_record'], 'Codex output outside response')
        record,ref=read_file(root,folder/'codex'/relative,sealed)
        message=record['message'];params=message['params']
        require(message['method']=='rawResponseItem/completed' and params['turnId']==request['native_turn_id'] and params['threadId']==request['session_id'], 'Codex output is not from this native turn')
        items.append(codex_evidence.project(params['item']));refs.append(ref)
    require(items==projected['output'], 'Codex semantic text differs from native output')
    return {'records':refs,'session':request['session_id'],'turn':request['native_turn_id']}


def delivered(root, registration, event, binding, step, *, sealed):
    from phase1.carrier_trace_review import read_file,require
    root=Path(root).resolve();folder=root/'natural'/event['actor']
    request,_=read_file(root,folder/'trace'/f'{step:04d}.request.json',sealed)
    refs=[]
    for path in sorted((folder/'codex/native').glob('*.json')):
        if str(path.relative_to(folder/'codex'))>=request['native_record']:break
        record,ref=read_file(root,path,sealed)
        message=record['message'];params=message.get('params') or {};item=params.get('item') or {}
        if message.get('method')!='rawResponseItem/completed' or item.get('type')!='function_call_output' or item.get('call_id')!=binding['call_id']:continue
        require(params['threadId']==request['session_id'] and json.loads(codex_evidence.mcp_output_text(item['output']))==event['result'], 'Codex rendered carrier return differs')
        refs.append(ref)
    require(len(refs)==1,'Exact Codex carrier result not delivered before interpretation')
    return refs
