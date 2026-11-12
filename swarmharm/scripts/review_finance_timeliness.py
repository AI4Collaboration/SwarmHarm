#!/usr/bin/env python3
"""Read-only, evidence-bound review of retained timed-payables delivery times."""
import argparse
import ast
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path


def load(path): return json.loads(path.read_text())
def digest(path): return sha256(path.read_bytes()).hexdigest()
def instant(text):
    value=datetime.fromisoformat(text.replace('Z','+00:00'))
    if value.tzinfo is None: raise ValueError('Timestamp lacks a timezone')
    return value

def timing(opened, deadline_seconds, published):
    opened,published=instant(opened),instant(published)
    elapsed=(published-opened).total_seconds()
    if elapsed < 0: raise ValueError('Publication predates activation')
    return {'deadline':(opened+timedelta(seconds=deadline_seconds)).isoformat(),
            'elapsed_seconds':round(elapsed,6), 'late_seconds':round(max(0,elapsed-deadline_seconds),6),
            'on_time':elapsed<=deadline_seconds}

def review(root):
    root=Path(root).resolve();reg=load(root/'registration.json');manifest=load(root/'evidence-manifest.json')
    if sha256((root/'registration.json').read_bytes()).hexdigest()!=load(root/'registration-seal.json')['sha256'] or manifest['registration_sha256']!=digest(root/'registration.json'):
        raise ValueError('Registration seal or evidence manifest mismatch')
    def protected(rel):
        p=root/rel
        if rel not in manifest['files'] or p.is_symlink() or not p.is_file() or digest(p)!=manifest['files'][rel]:
            raise ValueError('Evidence manifest mismatch: '+rel)
        return p
    code='swarmharm/phase2/delivery_payables_timed.py';codepath=root/'code'/code
    if digest(codepath)!=reg['code_hashes'][code]:raise ValueError('Frozen timing code hash mismatch')
    tree=ast.parse(codepath.read_text());values=[n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEADLINE_SECONDS' for t in n.targets) and isinstance(n.value,ast.Constant)]
    if len(values)!=1 or not isinstance(values[0],int) or values[0]<=0:raise ValueError('Deadline not uniquely registered in frozen code')
    deadline=values[0];activation=load(protected('natural/activation.json'))['activated_at'];world=load(protected('natural/world.json'));events=world['events'];starts=[e for e in events if e['operation']=='payables_cycle_started']
    if len(starts)!=1 or starts[0]['arguments']['started_at']!=activation:raise ValueError('Activation differs from cycle event')
    def event_protected(event):
        recorded=load(protected(f"natural/operator/tool-commits/{event['id']:06d}.json"))['event']
        if recorded!=event:raise ValueError('Event does not match protected tool commit')
    event_protected(starts[0]);actors=reg['phase2']['assignments'];by_actor={a:[] for a in actors}
    for e in events:
        if e['operation'] in ('release_payables_close','withdraw_payables_close') and e.get('actor') in actors:
            event_protected(e);by_actor[e['actor']].append(e)
    atif=load(root/'atif-validation.json'); validated={x['actor']:x for x in atif['trajectories'] if x['phase']=='natural'}
    rows=[]
    for actor,assignment in actors.items():
        account=assignment['account'];last=None
        for e in by_actor[actor]:
            if e['result'].get('status')==201 and e['operation']=='release_payables_close':last=e
            if e['result'].get('status')==200 and e['operation']=='withdraw_payables_close':last=None
        if last is None:
            rows.append({'actor':actor,'account':account,'status':'not_retained','deadline':(instant(activation)+timedelta(seconds=deadline)).isoformat()});continue
        receipt=load(protected('natural/operator/delivery-files/payables/published/'+account+'.json'))
        if receipt!={k:v for k,v in last['result'].items() if k!='status'}:raise ValueError('Retained receipt differs from release event')
        csvpath=protected('natural/operator/delivery-files/payables/published/'+account+'.csv')
        if digest(csvpath)!=receipt['sha256']:raise ValueError('Retained delivery differs from its receipt')
        record=validated.get(actor)
        if not record or not record.get('native_continuity_passed'):raise ValueError('ATIF continuity failed')
        trajectory=root/record['path']
        if digest(trajectory)!=record['sha256']:raise ValueError('ATIF hash mismatch')
        steps=load(trajectory)['steps']; matches=[]
        for step in steps:
            if step.get('extra',{}).get('native_request')!=f"trace/{last['step']:04d}.request.json":continue
            for call in step.get('tool_calls',[]):
                if call.get('function_name')!='release_payables_close' or call.get('arguments')!=last['arguments']:continue
                ident=call['tool_call_id'];results=[x for x in step.get('observation',{}).get('results',[]) if x.get('source_call_id')==ident]
                delivery=step.get('extra',{}).get('tool_result_delivery',{}).get(ident,{})
                if len(results)!=1 or json.loads(results[0]['content'])!=last['result'] or not all(delivery.get(k) for k in ('sdk_delivery_verified','mcp_completion_verified','rendered_result_verified')):continue
                native=[]
                for file in delivery.get('native_records',[]):
                    item=load(protected(f'natural/{actor}/{file}')).get('message',{}).get('params',{}).get('item',{})
                    if item.get('type')=='mcpToolCall' and item.get('id')==ident and item.get('tool')=='release_payables_close':native.append(item)
                if len(native)!=1:continue
                item=native[0]; contents=item.get('result',{}).get('content',[])
                if item.get('arguments')!=last['arguments'] or len(contents)!=1 or json.loads(contents[0]['text'])!=last['result']:continue
                stamp=instant(last['at']).timestamp()*1000
                if not item['startedAtMs']-1000<=stamp<=item['completedAtMs']+1000:raise ValueError('Protected event timestamp differs from native call')
                matches.append((step['step_id'],ident))
        if len(matches)!=1:raise ValueError('Release event not uniquely bound to native call')
        rows.append({'actor':actor,'account':account,'status':'retained_release','reference':receipt['reference'],
                     'event_id':last['id'],'native_call_id':matches[0][1],'atif_step':matches[0][0],
                     'published_at':last['at'],**timing(activation,deadline,last['at'])})
    published=root/'natural/operator/delivery-files/payables/published'
    retained={row['account'] for row in rows if row['status']=='retained_release'}
    if {p.stem for p in published.glob('*.json')}!=retained or {p.stem for p in published.glob('*.csv')}!=retained:
        raise ValueError('Retained delivery files differ from audited releases')
    return {'schema':'finance-timeliness-review-v1','registration_sha256':digest(root/'registration.json'),
            'evidence_manifest_sha256':digest(root/'evidence-manifest.json'),'activation':activation,
            'deadline_seconds':deadline,'deadline_source':code,'results':rows,
            'retained_count':sum(r['status']=='retained_release' for r in rows),
            'late_count':sum(not r['on_time'] for r in rows if r['status']=='retained_release'),
            'scope':'Retained release timing only; no modification of original scores or attribution of cause.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('output_directory',type=Path);ap.add_argument('--report',type=Path,required=True);args=ap.parse_args()
    if args.report.resolve().is_relative_to(args.output_directory.resolve()):raise ValueError('Report must be outside frozen evidence')
    value=review(args.output_directory)
    with args.report.open('x') as output: output.write(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'retained':value['retained_count'],'late':value['late_count']}))
