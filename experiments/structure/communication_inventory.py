"""Operator-only inventory. Messages and process exposure are not authority edges."""
import argparse
import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

WRITE = re.compile(r'^(\d+)\s+(\d+\.\d+)\s+(write|pwrite64)\(\d+<([^>]+)>, "((?:\\x[0-9a-f]{2})*)", (\d+)(?:, (\d+))?\) = (\d+)$')


def writes(text):
    for number,line in enumerate(text.splitlines(),1):
        m=WRITE.fullmatch(line)
        if not m:continue
        pid,at,op,raw_path,encoded,requested,offset,returned=m.groups()
        path=re.sub(r'\\x([0-9a-f]{2})',lambda m:chr(int(m[1],16)),raw_path)
        data=bytes.fromhex(encoded.replace('\\x',''))
        count=int(returned)
        if not path.startswith('/var/tmp/exports/') or not 0<count<=len(data):continue
        yield {'line':number,'pid':int(pid),'at_unix':at,'operation':op,'path':path,
               'bytes_written':count,'data':data[:count]}


def objects(text):
    decoder=json.JSONDecoder();position=0
    def walk(v):
        if isinstance(v,dict):
            yield v
            for x in v.values():yield from walk(x)
        elif isinstance(v,list):
            for x in v:yield from walk(x)
    while position<len(text):
        begin=text.find('{',position)
        if begin<0:return
        try:v,end=decoder.raw_decode(text,begin)
        except ValueError:position=begin+1;continue
        yield from walk(v);position=end


def envelopes(text):
    for row in objects(text):
        if all(isinstance(row.get(k),str) for k in ('sender','recipient','text')):
            yield {k:row[k] for k in ('sender','recipient','text')}


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def inventory(root, native_overrides=None):
    root=Path(root).resolve()
    if not (root/'completion.json').exists():raise ValueError('Closed runs only')
    sys.path[:0]=[str(root/'code/experiments/swarmharm-v1'),str(root/'code/experiments/runtime')]
    from swarmform.read_observer import observed_reads
    reg=json.loads((root/'registration.json').read_text())
    messages=[];receipts=[];texts=[];native={};trace_refs={};other_publications=[]
    for actor in reg['plan']['natural']:
        folder=root/'read-observations'/actor
        observation=sorted(folder.glob('*.json'))[-1]
        manifest=json.loads(observation.read_text());seen=set()
        trace_refs[str(observation.relative_to(root))]=sha256(observation.read_bytes()).hexdigest()
        for item in manifest['files'].values():
            if item['sha256'] in seen:continue
            seen.add(item['sha256']);path=folder/item['blob'];raw=path.read_bytes()
            if sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Trace hash mismatch')
            trace_refs[str(path.relative_to(root))]=item['sha256']
            text=raw.decode(errors='replace')
            for event in writes(text):
                content=event.pop('data');decoded=content.decode(errors='replace')
                ref={**event,'actor':actor,'blob':str(path.relative_to(root)),
                     'blob_sha256':item['sha256'],'content_sha256':sha256(content).hexdigest(),
                     'at':datetime.fromtimestamp(float(event['at_unix']),timezone.utc).isoformat()}
                found=list(envelopes(decoded))
                for envelope in found:
                    messages.append({**ref,'envelope':envelope,'message_key':digest(envelope),
                                     'claimed_sender_matches_writer':envelope['sender']==actor})
                if not found and event['path'].lower().endswith(('.md','.txt','.py','.sh')):
                    other_publications.append({**ref,'text':decoded})
            for event in observed_reads(text):
                content=base64.b64decode(event['data_base64'],validate=True)
                for envelope in envelopes(content.decode(errors='replace')):
                    receipts.append({k:v for k,v in event.items() if k!='data_base64'}|
                        {'receiver':actor,'message_key':digest(envelope),'envelope':envelope,
                         'blob':str(path.relative_to(root)),'blob_sha256':item['sha256']})
        session=(native_overrides or {}).get(actor,root/'natural'/actor/'codex/session.jsonl')
        session=Path(session).resolve();raw=session.read_bytes()
        calls=[];statements=[];outputs=[]
        for line_number,line in enumerate(raw.decode().splitlines(),1):
            event=json.loads(line);payload=event.get('payload',{})
            if event.get('type')!='response_item':continue
            ref={'line':line_number,'at':event.get('timestamp')}
            if event.get('source_native_record'):
                ref['source_native_record']=event['source_native_record']
            if payload.get('type')=='function_call':
                calls.append(ref|{'call_id':payload.get('call_id'),'name':payload.get('name'),
                                 'arguments':payload.get('arguments')})
            elif payload.get('type')=='message' and payload.get('role')=='assistant':
                statements.append(ref|{'phase':payload.get('phase'),
                    'text':'\n'.join(p.get('text','') for p in payload.get('content',[]))})
            elif payload.get('type')=='function_call_output':
                value=payload.get('output');parts=value if isinstance(value,list) else [{'text':str(value)}]
                decoded=[]
                for part in parts:
                    t=part.get('text','');decoded.append(t)
                    try:j=json.loads(t)
                    except (ValueError,TypeError):continue
                    if isinstance(j,dict):decoded.extend(str(j.get(k,'')) for k in ('stdout','stderr'))
                outputs.append(ref|{'call_id':payload.get('call_id'),'text':'\n'.join(decoded)})
        native[actor]={'path':str(session.relative_to(root)),'sha256':sha256(raw).hexdigest(),
                       'calls':calls,'assistant_statements':statements,'tool_outputs':outputs,
                       'source_kind':'derived_raw_event_index' if actor in (native_overrides or {}) else 'session_export'}
    messages.sort(key=lambda m:(float(m['at_unix']),m['actor'],m['line']))
    for index,msg in enumerate(messages):
        msg['id']=f'm{index+1:04d}'
        msg['process_receipts']=[r for r in receipts if r['message_key']==msg['message_key']
            and r['receiver']!=msg['actor'] and float(r['at_unix'])>float(msg['at_unix'])]
        msg['native_output_exposures']=[]
        msg['same_text_message_keys']=sorted({other['message_key'] for other in messages if other['envelope']['text']==msg['envelope']['text']})
        for actor,records in native.items():
            if actor==msg['actor']:continue
            for output in records['tool_outputs']:
                if datetime.fromisoformat(output['at'].replace('Z','+00:00'))<=datetime.fromisoformat(msg['at']):continue
                value=msg['envelope']['text']
                # Exact nontrivial plaintext or JSON-escaped text, not a path/name match.
                if len(value.strip())>=20 and (value in output['text'] or json.dumps(value)[1:-1] in output['text']):
                    msg['native_output_exposures'].append({'actor':actor,'path':records['path'],
                        'sha256':records['sha256'],'line':output['line'],'at':output['at'],
                        'call_id':output['call_id'],'scope':'Exact text content exposure; identical message texts cannot identify a unique envelope.'})
    return {'registration_id':reg['identifier'],'method_version':2,
        'analysis_code_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'messages':messages,'other_text_publications':other_publications,'native':native,
        'trace_hashes':trace_refs,'status':'inventory_for_semantic_review',
        'scope':'Successful complete scalar writes of recognized JSON envelopes; subsequent exact process reads and exact native tool-output exposure are distinct. Actual writer, claimed sender and intended recipient remain separate. Other encodings, split writes, partial text and unparsed syscalls can be missed. Native exposure is neither comprehension nor adoption. No orchestrator or communication-absence verdict follows from this inventory.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Preserve prior review')
    report=inventory(args.run);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'registration_id':report['registration_id'],'messages':len(report['messages']),
        'other_text_publications':len(report['other_text_publications']),
        'native_calls':sum(len(v['calls']) for v in report['native'].values())}))


if __name__=='__main__':main()
