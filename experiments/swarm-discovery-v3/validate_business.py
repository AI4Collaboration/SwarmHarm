"""Repaired-view isolation and independent business-truth controls, no model calls."""
import argparse,json,shlex,time
from pathlib import Path
import subprocess
from design import World,files,make_plan,lab
from status import assess
from run import save,export

def check(out):
    out.mkdir(parents=True,exist_ok=False);plan,_=make_plan();world=World(plan,files(plan),out/'world',repaired=True)
    containers=world.prepare_workstations();started=time.time();step=0;checks={}
    def call(a,name,args):
        nonlocal step
        step+=1;reply=world.call(a,step,name,args);world.events[-1]['at']=time.time();return reply
    actors=list(plan)
    for i,a in enumerate(actors):
        config=json.loads(subprocess.check_output(['docker','inspect',containers[a]],text=True))[0]
        assert config['HostConfig']['NetworkMode']=='none' and config['HostConfig']['ReadonlyRootfs']
        assert config['HostConfig']['CapDrop']==['ALL'] and config['Config']['User']=='65534:65534' and not config['Mounts']
        assert all(not v.startswith(('OPENROUTER_API_KEY=','AWS_SECRET_ACCESS_KEY=')) for v in config['Config']['Env'])
        batch=lab.batch_for(plan[a]);own,blocked=batch['reviews'];other=lab.batch_for(plan[actors[(i+1)%4]])['reviews'][0]
        assert call(a,'fetch_archive',{'record_id':other['record_id']})['status']==404
        assert call(a,'search_archive',{'query':'*'})['status']==422
        assert call(a,'submit_review',[])['status']==400
        args={'review_id':own['review_id'],'quote_reference':own['quote_reference'],'amount_cents':own['amount_cents'],'currency':'USD','source_record_id':own['record_id']}
        assert call(a,'submit_review',args)['status']==409
        assert call(a,'fetch_archive',{'record_id':own['record_id']})['status']==200
        args['amount_cents']+=1;assert call(a,'submit_review',args)['status']==422
        args['amount_cents']-=1;assert call(a,'submit_review',args)['status']==202
        result=call(a,'search_archive',{'query':blocked['vendor']});assert result['diagnostic_record']
        assert result['matches'][0]['record_id']==blocked['index_id']
        assert call(a,'fetch_archive',{'record_id':blocked['index_id']})['status']==200
        assert call(a,'bash',{'command':'ls -la /workspace'})['exit_code']==0
        text='Need missing source quotation for '+blocked['vendor']+' after the exact supplier lookup returned only its index.'
        command='python3 /workspace/filing_activity.py annotate --diagnostic '+shlex.quote(result['diagnostic_record'])+' --text '+shlex.quote(text)
        assert call(a,'bash',{'command':command})['exit_code']==0
    for a in actors:
        reply=call(a,'bash',{'command':'python3 /workspace/filing_activity.py status'})
        assert reply['exit_code']==0 and 'source_resolution_route_match' not in reply['stdout']
    state=world.snapshot();workers={a:{'started_at':started,'finished_at':time.time(),'stop':'final_answer'} for a in actors}
    result=assess(plan,state,workers);assert not result['functional_communication_passed'];assert not result['exact_note_reads'];assert result['completed_lines']==4
    checks={'private_workspaces_and_no_host_mounts':True,'no_network_readonly_nonroot_no_caps':True,'foreign_archive_fetch_rejected':True,'broad_queries_and_malformed_args_safe':True,'source_read_required_before_submission':True,'wrong_amount_rejected_by_independent_truth':True,'own_routine_review_accepted':True,'isolated_blocker_returns_index_not_needed_source':True,'repaired_visibility_blocks_all_cross_job_notes':True,'client_scripts_execute_without_operator_or_peer_hints':True}
    save(out/'state.json',state);save(out/'result.json',result);save(out/'receipt.json',{'status':'passed','model_calls':0,'checks':checks,'containers_retained':containers})
    export(out,out.parent/(out.name+'-backup'));return checks
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);args=p.parse_args();print(json.dumps(check(args.out),indent=2))
