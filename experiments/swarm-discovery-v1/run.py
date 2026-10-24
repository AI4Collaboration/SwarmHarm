"""Prepare a new immutable input, or collect it once. No inference retries."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

HERE=Path(__file__).resolve().parent
from design import SYSTEM,TASK,TOOLS,IMAGE,fixtures,initial_files
from review import assess
from world import World
import emit_harbor as harbor_inputs
sys.path.insert(0,str(HERE.parent/'back-office-v1'))
from durability import append, atomic_bytes, export, hashes, pending, save
sys.path.insert(0,str(HERE.parent/'error-propagation-v3'))
import transport
# Process-local tool configuration; neither historical sources nor other runs change.
transport.TOOLS=TOOLS
MODEL='deepseek/deepseek-v4.1-flash-1017'
PROVIDER='novita/fp8'
SOURCE_FILES=sorted(HERE.glob('*.py'))+[HERE/'protocol.json']
SOURCE_FILES += [HERE.parent/'back-office-v1'/n for n in ('durability.py','run_model.py')]
SOURCE_FILES += [HERE.parent/'error-propagation-v3'/'transport.py',HERE.parent/'prompt-contract'/'checks.py']


def source_hashes():
    return {str(p.relative_to(HERE.parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE_FILES}


def preflight():
    def get(path):
        req=urllib.request.Request('https://openrouter.ai/api/v1/'+path,headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    key=get('key')['data']
    routes=get('models/deepseek/deepseek-v4.1-flash-1017/endpoints')['data']
    endpoints=[e for e in routes['endpoints'] if e.get('tag')==PROVIDER and e.get('quantization')=='fp8' and {'tools','reasoning','max_tokens'}<=set(e.get('supported_parameters',[]))]
    if not endpoints:raise RuntimeError('pinned Novita route unavailable; no fallback')
    return {'checked_at':time.time(),'model':MODEL,'provider':PROVIDER,'endpoints':endpoints,
            'credential_available':True,'credential_scope':'existing authorized private OpenRouter configuration',
            'key_disabled':bool(key.get('is_disabled',False))}


def validation_gate():
    path=HERE/'VALIDATION.json'
    evidence=json.loads(path.read_text())
    if evidence.get('status')!='passed' or evidence['source_sha256']!=source_hashes():
        raise RuntimeError('offline validation missing or stale; no preparation')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out,backup,seed):
    out=out.resolve();backup=backup.resolve()
    if out==backup or out in backup.parents or backup in out.parents:raise ValueError('disjoint backup required')
    if out.exists() or backup.exists():raise FileExistsError('new output and backup directories required')
    if subprocess.check_output(['git','-C',str(HERE.parents[1]),'status','--porcelain']).strip():raise RuntimeError('commit code before freezing')
    validation_sha256=validation_gate()
    routes=preflight()
    if routes['key_disabled']:raise RuntimeError('credential disabled')
    out.mkdir(parents=True,mode=0o700)
    fixture=fixtures(seed)
    registration={'study':'swarm-discovery-v1','created_at':time.time(),'model':MODEL,'provider':PROVIDER,
        'model_route':routes,'validation_sha256':validation_sha256,'image':IMAGE,'code_commit':subprocess.check_output(['git','-C',str(HERE.parents[1]),'rev-parse','HEAD'],text=True).strip(),
        'source_sha256':source_hashes(),'population':len(fixture['actors']),'seed':seed,
        'budget':{'max_calls_per_agent':40,'max_generated_tokens_per_agent':131072,'max_tokens_per_call':8192,'wall_seconds':1200,'reasoning_effort':'high','request_timeout_seconds':300},
        'system':SYSTEM,'task':TASK,'tools':TOOLS,'pressure':False,'repaired':False,
        'terminal_final_answers':True,'queue_or_peer_notifications':False,
        'tool_scheduling':'serialized file transactions; four independent model requests overlap',
        'publication_path':'experiments/swarm-discovery-v1/registrations/2026-10-24-pilot-r1/registration.json',
        'publication_branch':subprocess.check_output(['git','-C',str(HERE.parents[1]),'branch','--show-current'],text=True).strip(),'fixture_sha256':hashlib.sha256(json.dumps(fixture,sort_keys=True).encode()).hexdigest(),
        'publication_rule':'no raw reasoning or credentials; summaries only',
        'operator_route':'OpenRouter only, existing user instruction; no AxonHub or EC2 use'}
    save(out/'registration.json',registration);save(out/'fixture.json',fixture)
    harbor_inputs.emit(out/'tasks',fixture)
    registration['task_hashes']=hashes(out/'tasks');save(out/'registration.json',registration)
    save(out/'recovery-index.json',{'episodes':[{'id':a,'dir':'trial/agents/'+a,'status':'registered'} for a in fixture['actors']],
          'containers':{},'backup_locations':[str(backup)],'unresolved_requests':[],
          'recovery_rule':'Never replay an unknown request or unfinished shell. This collector is one-shot, not resumable.'})
    export(out,backup)
    return registration


def verify_public_registration(out,reg):
    raw=(out/'registration.json').read_bytes()
    expected=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    remote=subprocess.check_output(['gh','api','repos/AI4Collaboration/SwarmHarm/contents/'+reg['publication_path']+'?ref='+reg['publication_branch'],'--jq','.sha'],text=True).strip()
    if remote!=expected:raise RuntimeError('published registration differs; no inference permitted')


def collect(out):
    out=out.resolve();reg=json.loads((out/'registration.json').read_text());fixture=json.loads((out/'fixture.json').read_text())
    if (out/'started.json').exists():raise RuntimeError('already started; reconcile existing evidence, never rerun')
    assert source_hashes()==reg['source_sha256'],'frozen source changed'
    assert validation_gate()==reg['validation_sha256'],'validation receipt changed'
    assert hashes(out/'tasks')==reg['task_hashes'],'frozen task changed'
    assert hashlib.sha256(json.dumps(fixture,sort_keys=True).encode()).hexdigest()==reg['fixture_sha256']
    assert reg['model']==MODEL and reg['provider']==PROVIDER
    # Require that the frozen implementation exists remotely before any inference.
    remote=subprocess.check_output(['git','-C',str(HERE.parents[1]),'ls-remote','origin',reg['code_commit']],text=True)
    if not remote:
        # ls-remote does not generally enumerate arbitrary reachable commits.
        subprocess.run(['gh','api','repos/AI4Collaboration/SwarmHarm/commits/'+reg['code_commit'],'--jq','.sha'],check=True,capture_output=True)
    verify_public_registration(out,reg)
    save(out/'started.json',{'at':time.time(),'code_commit':reg['code_commit']})
    trial=out/'trial';trial.mkdir();backup=Path(json.loads((out/'recovery-index.json').read_text())['backup_locations'][0]);lock=threading.Lock();hold=threading.Event()
    budget=reg['budget'];barrier=threading.Barrier(len(fixture['actors']));workers={}
    def checkpoint(world):
        save(trial/'world'/'state.json',world.state())
        export(trial/'world',backup/'trial'/'world')
    world=World(fixture,trial/'world',checkpoint=checkpoint);world.start()
    save(trial/'containers.json',world.containers)
    def update():
        with lock:
            save(out/'recovery-index.json',{'episodes':[{'id':a,'dir':'trial/agents/'+a,
               'status':'complete' if 'finished_at' in workers.get(a,{}) else 'running',**dict(workers.get(a,{}))} for a in fixture['actors']],
               'containers':world.containers,'backup_locations':[str(backup)],'unresolved_requests':pending(trial),
               'recovery_rule':'No replay. Model final answers are terminal; no global completion gate or wakeup.'})
    def worker(actor):
        folder=trial/'agents'/actor;folder.mkdir(parents=True)
        journal=folder/'journal.jsonl';messages=[{'role':'system','content':SYSTEM},{'role':'user','content':TASK}]
        append(journal,{'kind':'episode_started','messages':deepcopy(messages)})
        save(folder/'messages.json',messages)
        state={'started_at':time.time(),'stop':'running','calls':0,'completion_tokens':0};workers[actor]=state
        chat=transport.DurableChat(MODEL,PROVIDER,max_tokens=budget['max_tokens_per_call'],reasoning_effort=budget['reasoning_effort'],timeout=budget['request_timeout_seconds']);chat.journal=journal
        barrier.wait(timeout=30);deadline=time.monotonic()+budget['wall_seconds'];chat.deadline=deadline
        try:
            while state['calls']<budget['max_calls_per_agent']:
                if hold.is_set():state['stop']='unresolved_request_hold';break
                if time.monotonic()>=deadline:state['stop']='wall_clock';break
                remaining=budget['max_generated_tokens_per_agent']-state['completion_tokens']
                if remaining<1024:state['stop']='token_budget';break
                chat.body['max_tokens']=min(remaining,budget['max_tokens_per_call']);state['calls']+=1
                try:message,metadata=chat(messages)
                except Exception as error:
                    state['stop']='api_error';hold.set();append(journal,{'kind':'api_error','error':type(error).__name__,'detail':str(error)});break
                append(journal,{'kind':'assistant_response','message':message,'metadata':metadata,'wave':1,'stage':0,'turn':state['calls'],'agent':actor})
                tokens=(metadata.get('usage') or {}).get('completion_tokens')
                if type(tokens) is not int or not 0<=tokens<=chat.body['max_tokens']:
                    state['stop']='accounting_error';hold.set();break
                state['completion_tokens']+=tokens
                kept={'role':'assistant','content':message.get('content')}
                if message.get('tool_calls'):kept['tool_calls']=message['tool_calls']
                if message.get('reasoning_details'):kept['reasoning_details']=message['reasoning_details']
                messages.append(kept);append(journal,{'kind':'assistant_kept'})
                save(folder/'messages.json',messages);export(folder,backup/'trial'/'agents'/actor)
                if not message.get('tool_calls'):
                    state['stop']='final_answer' if metadata['finish_reason']=='stop' else 'truncated_response';break
                for call in message['tool_calls']:
                    if hold.is_set():state['stop']='unresolved_request_hold';break
                    append(journal,{'kind':'tool_prepared','call':call})
                    try:
                        args=json.loads(call['function']['arguments'])
                        result=world.call(actor,call['function']['name'],args)
                    except (ValueError,TypeError,KeyError) as error:result={'status':400,'error':str(error)}
                    except subprocess.TimeoutExpired:
                        state['stop']='unknown_tool';hold.set();break
                    except Exception as error:
                        state['stop']='observer_error';hold.set();append(journal,{'kind':'observer_error','error':type(error).__name__,'detail':str(error)});break
                    append(journal,{'kind':'tool_result','call_id':call['id'],'result':result,'actor':actor,'wave':1,'stage':0})
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
                    save(folder/'messages.json',messages);export(folder,backup/'trial'/'agents'/actor)
                if state['stop']!='running':break
                if metadata['finish_reason']=='length':state['stop']='truncated_response';break
            else:state['stop']='call_budget'
        finally:
            state['finished_at']=time.time()
            append(journal,{'kind':'episode_ended',**state})
            save(folder/'meta.json',{'model':MODEL,'stop':state['stop'],'grading_status':'pending_independent_review',
                  'episode_complete':state['stop']=='final_answer','unresolved_api_requests':pending(folder),**state})
            export(folder,backup/'trial'/'agents'/actor);update()
        return actor,state
    failures=[]
    with ThreadPoolExecutor(max_workers=len(fixture['actors'])) as pool:
        futures={pool.submit(worker,a):a for a in fixture['actors']}
        for future in as_completed(futures):
            try:actor,state=future.result();print(json.dumps({'agent':actor,**state}),flush=True)
            except Exception as error:
                hold.set();failures.append({'agent':futures[future],'error':type(error).__name__,'detail':str(error)})
    save(trial/'workers.json',workers)
    if failures:save(trial/'collection-errors.json',failures)
    result=assess(fixture,world.state(),workers)
    if failures:result.update(grading_status='grading_error',formation_passed=None,collection_errors=failures)
    save(trial/'result.json',result);update();export(out,backup)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','collect'])
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--backup',type=Path);parser.add_argument('--seed',type=int,default=20261024)
    args=parser.parse_args()
    if args.action=='prepare':
        if args.backup is None:parser.error('--backup is required')
        result=prepare(args.out,args.backup,args.seed)
    else:result=collect(args.out)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
