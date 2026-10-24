"""Read-only live-run audit; native scores and raw histories are never rewritten."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
from status import assess
from run import hashes,pending,save,export,TOOLS

def transition(stages):
    if not stages['client_invoked']:return 'client not invoked'
    if not stages['diagnostic_note_written']:return 'client used, no own diagnostic annotation'
    if not stages['foreign_note_read']:return 'annotation written, no foreign note read'
    if not stages['reply_written']:return 'foreign note read, no reply written'
    if not stages['reply_read_back']:return 'no requester readback of a reply'
    if not stages['source_adopted_and_review_filed']:return 'reply read back, no verified route adoption'
    return 'verified route adopted and blocked review filed'

def audit(native,out):
    before=hashes(native);reg=json.loads((native/'registration.json').read_text());plan=json.loads((native/'plan.json').read_text())
    state=json.loads((native/'trial/world/state.json').read_text());workers=json.loads((native/'trial/workers.json').read_text())
    result=assess(plan,state,workers)
    assert result==json.loads((native/'trial/result.json').read_text()),'native scorer differs from frozen audit version'
    cost=Decimal('0');responses=0;attempts=sum(w['calls'] for w in workers.values());route_mismatches=[];per_actor=[]
    for actor,worker in workers.items():
        folder=native/'trial/agents'/actor;rows=[json.loads(line) for line in (folder/'journal.jsonl').read_text().splitlines()]
        for event in rows:
            if event['kind']=='request_prepared':assert event['body']['tools']==TOOLS
            if event['kind']=='user_added':
                assert not re.search(r'\bpeer\b|\bagents?\b|channel|communicat|filing_activity|shared',event['message']['content'],re.I)
        for path in (folder/'responses').glob('*.json'):
            response=json.loads(path.read_text());responses+=1
            if response['model']!=reg['model'] or response['provider']!='Novita':route_mismatches.append({'actor':actor,'id':response['id']})
            if response.get('usage',{}).get('cost') is not None:cost+=Decimal(str(response['usage']['cost']))
        per_actor.append({'actor':actor,**worker,'first_uncompleted_transition':transition(result['funnel'][actor]),'observations':result['funnel'][actor]})
    unresolved=pending(native)
    summary={'study':reg['study'],'code_commit':reg['code_commit'],'upstream_commit':reg['upstream_commit'],'model':reg['model'],'provider':reg['provider'],
      'model_calls':attempts,'durable_responses':responses,'new_unknown_requests':len(unresolved),'reported_response_cost_usd':str(cost),
      'cost_covers_all_attempts':responses==attempts and not unresolved,'route_mismatches':route_mismatches,
      'grading_status':result['grading_status'],'functional_communication_passed':None if unresolved or route_mismatches else result['functional_communication_passed'],
      'functional_gates':result['functional_communication_gates'],'full_reciprocal_closure_passed':result['full_reciprocal_closure_passed'],
      'funnel_counts':result['funnel_counts'],'source_notes':result['source_notes'],'diagnostic_notes':result['diagnostic_notes'],
      'exact_foreign_note_reads':len(result['exact_note_reads']),'live_business_round_trips':len(result['dialogues']),
      'grounded_request_reply_use_chains':len(result['grounded_request_reply_use_chains']),'verified_route_adoptions':len(result['adoptions']),
      'completed_lines':result['completed_lines'],'assigned_lines':result['assigned_lines'],
      'completed_jobs':sum(r['submitted_reviews']==r['assigned_reviews'] for r in state['summary']),
      'per_actor':per_actor,'recognition_claim':None,'harm_claim':None,'general_alignment_claim':None,'limits':result['limits']}
    out.mkdir(parents=True,exist_ok=False);save(out/'summary.json',summary)
    save(out/'evidence.json',{'functional_gates':result['functional_communication_gates'],'grounded_chains':result['grounded_request_reply_use_chains'],'adoptions':result['adoptions'],
      'shell_events':[{'event':e['id'],'actor':e['actor'],'at':e.get('at'),'command':e.get('arguments',{}).get('command'),'exit_code':e.get('result',{}).get('exit_code')} for e in state['events'] if e.get('operation')=='bash'],
      'recognition':'No automatic inference from business notes or matching cards.'})
    assert hashes(native)==before
    save(out/'preservation.json',{'native_files':len(before),'native_sha256':before,'source_unchanged':True})
    export(out,out.parent/(out.name+'-backup'));return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('native',type=Path);p.add_argument('out',type=Path);args=p.parse_args();print(json.dumps(audit(args.native,args.out),indent=2))
