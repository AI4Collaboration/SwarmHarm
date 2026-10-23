"""Export completed native Chat Completions collections; never changes native data."""
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime,timezone
from harbor.models.trajectories import Trajectory

BASE=Path(sys.argv[1]).resolve()
OUT=Path(sys.argv[2]).resolve()


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def export_episode(folder,destination):
    meta=json.loads((folder/'meta.json').read_text())
    journal=folder/'journal.jsonl'
    events=[json.loads(x) for x in journal.read_text().splitlines()]
    first=next(e for e in events if e['kind']=='episode_started')
    expected=list(first['messages']);steps=[];used=[];current=None;raw=None;assistant=None;last=None;request_count=0
    source_hashes={'journal.jsonl':sha(journal),'messages.json':sha(folder/'messages.json'),'meta.json':sha(folder/'meta.json')}
    for message in expected:
        steps.append({'step_id':len(steps)+1,'source':message['role'],'message':message['content']})
    for event in events:
        kind=event['kind']
        if kind=='user_added':
            expected.append(event['message'])
            steps.append({'step_id':len(steps)+1,'source':'user','message':event['message']['content'], 'extra':{'wave':event['wave'],'stage':event['stage']}})
        elif kind=='request_prepared':
            assert event['body']['messages']==expected,'Request continuity mismatch'
            current=event;raw=None;request_count+=1
        elif kind=='response_saved':
            path=Path(event['path']);raw=json.loads(path.read_text())
            source_hashes[str(path.relative_to(folder))]=sha(path)
            assert event['request_id']==current['request_id']
        elif kind=='assistant_response':
            assistant=event['message'];metadata=event['metadata']
            assert raw['choices'][0]['message']==assistant,'Raw assistant response mismatch'
            last={'step_id':len(steps)+1,'source':'agent','message':assistant.get('content') or '',
                'model_name':metadata['model'],'reasoning_effort':current['body'].get('reasoning',{}).get('effort'),
                'llm_call_count':1,'timestamp':datetime.fromtimestamp(current['time'],timezone.utc).isoformat(),
                'extra':{'native_request_id':current['request_id'],'provider_response_id':metadata.get('id'),
                         'provider':metadata.get('provider'),'reported_cost_usd':metadata.get('cost')}}
            usage=metadata.get('usage') or {}
            last['metrics']={k:v for k,v in {'prompt_tokens':usage.get('prompt_tokens'),
              'completion_tokens':usage.get('completion_tokens'),'cached_tokens':(usage.get('prompt_tokens_details') or {}).get('cached_tokens')}.items() if v is not None}
            calls=[]
            for call in assistant.get('tool_calls') or []:
                text=call['function']['arguments'];extra={}
                try:
                    args=json.loads(text)
                    if not isinstance(args,dict):raise ValueError('not an object')
                except (ValueError,TypeError):
                    args={};extra={'native_invalid_arguments':text,'note':'Empty ATIF arguments are a schema placeholder; native arguments were malformed.'}
                c={'tool_call_id':call['id'],'function_name':call['function']['name'],'arguments':args}
                if extra:c['extra']=extra
                calls.append(c)
            if calls:last['tool_calls']=calls
            steps.append(last)
        elif kind=='assistant_kept':
            kept={'role':'assistant','content':assistant.get('content')}
            if assistant.get('tool_calls'):kept['tool_calls']=assistant['tool_calls']
            if current['body'].get('reasoning') and assistant.get('reasoning_details'):
                kept['reasoning_details']=assistant['reasoning_details']
            expected.append(kept)
        elif kind=='tool_result':
            assert last is not None
            call=next(c for c in assistant['tool_calls'] if c['id']==event['call_id'])
            text=json.dumps(event['result'])
            expected.append({'role':'tool','tool_call_id':event['call_id'],'content':text})
            last.setdefault('observation',{'results':[]})['results'].append({'source_call_id':event['call_id'],'content':text})
            used.append(event['call_id'])
    assert expected==json.loads((folder/'messages.json').read_text()),'Final native history mismatch'
    session=hashlib.sha256(str(folder.relative_to(BASE)).encode()).hexdigest()[:24]
    trajectory={'schema_version':'ATIF-v1.8','session_id':session,'trajectory_id':session+':primary',
       'agent':{'name':folder.name,'version':'error-propagation-v1','model_name':meta['model']},'steps':steps,
       'extra':{'native_episode':str(folder),'source_sha256':source_hashes,'native_continuity_passed':True,
                'stop':meta['stop'],'grading_status':meta['grading_status'],'episode_complete':meta['episode_complete'],
                'unresolved_api_requests':meta.get('unresolved_api_requests',[]),
                'conversion':'Raw reasoning remains in native records. No reasoning or missing response was invented. This is a native Docker runner, not a Harbor model execution.'}}
    validated=Trajectory.model_validate(trajectory).to_json_dict()
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    destination.write_text(json.dumps(validated,indent=2)+'\n')
    return {'source':str(folder),'destination':str(destination),'requests':request_count,'tool_results':len(used),
            'sha256':sha(destination),'native_continuity_passed':True,'schema':'ATIF-v1.8','harbor_version':'0.24.0'}


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    receipts=[]
    for meta in sorted(BASE.glob('*/agents/*/meta.json')):
        target=OUT/meta.parent.relative_to(BASE)/'agent/trajectory.json'
        receipt_path=target.parent/'export-receipt.json'
        if receipt_path.exists():
            receipts.append(json.loads(receipt_path.read_text()));continue
        receipt=export_episode(meta.parent,target)
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n');receipts.append(receipt)
    (OUT/'validation.json').write_text(json.dumps({'exports':receipts,'validated_exports':len(receipts)},indent=2)+'\n')
    print('Validated',len(receipts),'ATIF trajectories with native continuity checks.')
