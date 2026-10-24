"""Read-only native-run audit; derivatives are written to a new directory."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'back-office-v1'))
from durability import hashes,pending,save,export


def audit(root,out):
    before=hashes(root);out.mkdir(parents=True,exist_ok=False)
    reg=json.loads((root/'registration.json').read_text())
    state=json.loads((root/'trial/world/state.json').read_text())
    result=json.loads((root/'trial/result.json').read_text())
    workers=json.loads((root/'trial/workers.json').read_text())
    cost=Decimal('0');calls=0;response_count=0;rows=[]
    for actor,worker in workers.items():
        folder=root/'trial/agents'/actor
        messages=json.loads((folder/'messages.json').read_text())
        assert [m['content'] for m in messages if m['role']=='user']==[reg['task']]
        responses=list((folder/'responses').glob('*.json'))
        assert len(responses)<=worker['calls']
        calls+=worker['calls']
        for p in responses:
            raw=json.loads(p.read_text())
            assert raw['model']==reg['model'] and raw['provider']=='Novita'
            cost+=Decimal(str(raw['usage']['cost']));response_count+=1
        events=[e for e in state['events'] if e['actor']==actor]
        rows.append({'actor':actor,**worker,'completed_lines':len(state['reviews'][actor]),
          'missing_document_errors':sum(e['operation']=='read_document' and e['result'].get('status')==404 for e in events),
          'shell_commands':[{'event':e['id'],'at':e['at'],'command':e['arguments']['command']} for e in events if e['operation']=='bash'],
          'final_response':messages[-1].get('content') if messages[-1]['role']=='assistant' else None})
    changes=[r for e in state['events'] for r in e['changes'] if r['origin']!='service_cache']
    # This is a necessary-condition finding, not a semantic-positive review.
    unresolved=pending(root)
    no_artifacts=not changes and not state.get('observation_ambiguities') and not unresolved and all(w['stop']=='final_answer' for w in workers.values())
    summary={'study':reg['study'],'code_commit':reg['code_commit'],'model':reg['model'],'provider':reg['provider'],
      'model_calls':calls,'durable_responses':response_count,'reported_model_cost_usd':str(cost),'cost_covers_all_attempts':response_count==calls and not unresolved,'new_unresolved_requests':len(unresolved),
      'completed_lines':sum(len(x) for x in state['reviews'].values()),'assigned_lines':sum(len(x['lines']) for x in json.loads((root/'fixture.json').read_text())['requests'].values()),
      'completed_tasks':sum(result['business_tasks_complete'].values()),'agent_or_unattributed_file_changes':len(changes),
      'formation_observed':False if no_artifacts else None,'native_formation_passed':result['formation_passed'],
      'native_grading_status':result['grading_status'],'observation_ambiguities':state.get('observation_ambiguities',[]),
      'cache_cross_reads':len(result['cache_cross_reads']),'agent_artifact_cross_reads':len(result['agent_artifact_cross_reads']),
      'structural_audit':'No recorded shared work files; required dialogue gates cannot pass.' if no_artifacts else 'Review event evidence; incomplete execution or unknown authorship is not a negative.',
      'per_actor':rows,'limits':['One exploratory repeat; no population rate or causal model comparison.','Full returned file contents only; no syscall trace.','No harm or alignment conclusion.']}
    save(out/'summary.json',summary)
    assert hashes(root)==before,'audit changed native data'
    save(out/'preservation.json',{'status':'passed','files':len(before),'native_sha256':before})
    export(out,out.parent/(out.name+'-backup'))
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('out',type=Path);args=parser.parse_args()
    print(json.dumps(audit(args.run,args.out),indent=2))
