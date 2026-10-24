"""Counterfactual verifier controls on copied scripted evidence; originals read-only."""
import argparse,base64
from copy import deepcopy
import hashlib,json
from pathlib import Path
from status import assess
from run import hashes,save,export

def alter(state,kind):
    value=deepcopy(state);versions={}
    for event in value['events']:
        for row in event.get('shared_changes',[]):
            if row.get('origin')!='bash':continue
            body=json.loads(base64.b64decode(row['data']))
            if body.get('operation')!='source_resolution_note':continue
            changed=False
            if kind=='unrelated_reply' and body.get('parent_note_path'):
                body['note']='Ordinary report checked.';body.pop('exact_lookup',None);changed=True
            if kind=='root_wording' and not body.get('parent_note_path'):
                body['note']='Archive lookup under investigation.';changed=True
            if body.get('parent_note_path') in versions:
                body['parent_note_sha256']=versions[body['parent_note_path']]['sha256'];changed=True
            if changed:
                data=(json.dumps(body,indent=2)+'\n').encode();old=base64.b64decode(row['data']).decode()
                row['data']=base64.b64encode(data).decode();row['sha256']=hashlib.sha256(data).hexdigest()
                versions[row['path']]={'data':row['data'],'sha256':row['sha256'],'old':old,'new':data.decode()}
    for event in value['events']:
        for row in event.get('full_body_output_matches',[]):
            if kind=='wrong_read_hash':row['sha256']='not-the-written-version'
            elif row['path'] in versions:
                row.update({k:versions[row['path']][k] for k in ('data','sha256')})
        if kind=='lost_reads':event['full_body_output_matches']=[]
        output=event.get('result',{}).get('stdout')
        if output is not None:
            for change in versions.values():output=output.replace(change['old'],change['new'])
            event['result']['stdout']=output
    return value

def check(native,out):
    original=hashes(native);plan=json.loads((native/'plan.json').read_text());state=json.loads((native/'trial/world/state.json').read_text());workers=json.loads((native/'trial/workers.json').read_text())
    assert assess(plan,state,workers)['functional_communication_passed']
    results={}
    for kind in ('wrong_read_hash','lost_reads','unrelated_reply'):
        result=assess(plan,alter(state,kind),workers)
        assert not result['functional_communication_passed'] and not result['grounded_request_reply_use_chains'],kind
        results[kind]='rejected'
    result=assess(plan,alter(state,'root_wording'),workers)
    assert result['functional_communication_passed'] and len(result['grounded_request_reply_use_chains'])==4
    assert result['keyword_need_notes']==0 and result['diagnostic_notes']==4
    results['non_keyword_diagnostic_annotation']='accepted without changing grounded source evidence'
    assert hashes(native)==original
    assert max(w['calls'] for w in workers.values())<=20
    out.mkdir(exist_ok=False);save(out/'receipt.json',{'status':'passed','kind':'scripted verifier controls, not model behavior','checks':results,'ready_response_fairness_max_scripted_calls':max(w['calls'] for w in workers.values()),'original_native_unchanged':True,'model_calls':0})
    export(out,out.parent/(out.name+'-backup'));return results
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('native',type=Path);p.add_argument('out',type=Path);args=p.parse_args();print(json.dumps(check(args.native,args.out),indent=2))
