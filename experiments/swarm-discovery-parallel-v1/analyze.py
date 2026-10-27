"""Independent per-trial audit and ATIF export; failures remain unscored."""
import importlib.util,json,sys,subprocess
from decimal import Decimal
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'swarm-discovery-v3'))
from run import hashes,pending,save,export,verify
from status import assess


def analyze(native,out):
    before=hashes(native);reg=json.loads((native/'registration.json').read_text());workers=json.loads((native/'trial/workers.json').read_text())
    state=json.loads((native/'trial/world/state.json').read_text());plan=json.loads((native/'plan.json').read_text())
    score=assess(plan,state,workers);assert score==json.loads((native/'trial/result.json').read_text())
    cost=Decimal(0);count=0;mismatch=[]
    for path in native.glob('trial/agents/*/responses/*.json'):
        r=json.loads(path.read_text());count+=1;cost+=Decimal(str((r.get('usage') or {}).get('cost') or 0))
        if r.get('model')!=reg['model'] or r.get('provider','').lower().replace(' ','')!=reg['provider'].split('/')[0]:mismatch.append(r.get('id'))
    spec=importlib.util.spec_from_file_location('execution_audit',HERE.parent/'swarm-discovery-audit-v1/audit.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    cli=audit.audit(native,out/'execution-audit')
    unknown=pending(native)
    summary={'study':reg['study'],'cell':reg['cell'],'model':reg['model'],'provider':reg['provider'],'model_calls':sum(w['calls'] for w in workers.values()),'durable_responses':count,'reported_response_cost_usd':str(cost),'new_unknown_requests':len(unknown),'route_mismatches':mismatch,'grading_status':score['grading_status'],'functional_communication_passed':None if unknown or mismatch else score['functional_communication_passed'],'grounded_chains':len(score['grounded_request_reply_use_chains']),'full_reciprocal_closure_passed':score['full_reciprocal_closure_passed'],'completed_lines':score['completed_lines'],'assigned_lines':score['assigned_lines'],'funnel_counts':score['funnel_counts'],'reply_counts':cli['reply_counts'],'direct_client_actors':cli['counts']['direct_cli_attempted'],'model_visible_note_readers':cli['model_visible_note_readers'],'workers':workers,'native_scores_preserved':True,'off_machine_raw_backup':False}
    save(out/'summary.json',summary)
    atif=out/'atif'
    subprocess.run([sys.executable,str(HERE.parent/'swarm-discovery-v3/export_atif.py'),str(native),str(atif),'swarm-discovery-parallel-v1'],check=True,capture_output=True,text=True)
    assert hashes(native)==before
    save(out/'preservation.json',{'native_sha256':before,'source_unchanged':True})
    export(out,out.parent/(out.name+'-backup'));return summary

if __name__=='__main__':
    print(json.dumps(analyze(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
