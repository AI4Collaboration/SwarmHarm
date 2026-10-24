"""One-shot frozen business-client collection with persistent independent histories."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import queue
from pathlib import Path
import subprocess
import sys
import threading
import time

HERE=Path(__file__).resolve().parent
from design import IMAGE,SYSTEM,TOOLS,World,files,initial,make_plan,task
from status import completion,feedback,UPDATE,assess
from safe_runtime import UnknownExecution
sys.path.insert(0,str(HERE.parent/'back-office-v1'))
from durability import append,atomic_bytes,export,hashes,pending,save,verify
sys.path.insert(0,str(HERE.parent/'error-propagation-v3'))
import transport
transport.TOOLS=TOOLS
MODEL='deepseek/deepseek-v4.1-flash-1017'
PROVIDER='novita/fp8'
import os,urllib.request

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

SOURCES=sorted(HERE.rglob('*.py'))+[HERE/'protocol.json',HERE/'UPSTREAM.json']
SOURCES += [HERE.parent/'back-office-v1'/n for n in ('durability.py','run_model.py')]
SOURCES += [HERE.parent/'error-propagation-v3'/'transport.py',HERE.parent/'swarm-discovery-v2'/'run.py',HERE.parent/'prompt-contract'/'checks.py']

def source_hashes():return {str(p.relative_to(HERE.parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}
def validation_gate():
    data=json.loads((HERE/'VALIDATION.json').read_text())
    assert data['status']=='passed' and data['source_sha256']==source_hashes(),'missing or stale validation'
    return hashlib.sha256((HERE/'VALIDATION.json').read_bytes()).hexdigest()

def packages(root,plan,workspaces):
    from harbor.models.task.config import TaskConfig
    import tomllib
    for actor,item in plan.items():
        p=root/actor;p.mkdir(parents=True,exist_ok=False)
        (p/'instruction.md').write_text(task(item)+'\n')
        text=f'''schema_version = "1.4"
[task]
name = "swarmharm/filing-{actor}"
version = "3.0"
description = "Supplier exposure review"
[[task.authors]]
name = "SwarmHarm"
[metadata]
family = "swarm-discovery-v3"
execution_adapter = "experiments/swarm-discovery-v3/run.py"
generic_harbor_scheduler = false
[agent]
timeout_sec = 300
user = "65534"
[verifier]
timeout_sec = 60
[environment]
docker_image = "{IMAGE}"
network_mode = "no-network"
cpus = 1
memory_mb = 512
storage_mb = 128
'''
        (p/'task.toml').write_text(text);TaskConfig.model_validate(tomllib.loads(text))
        for name,data in workspaces[actor].items():
            import base64
            target=p/'environment'/name.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(base64.b64decode(data))
        save(p/'provenance.json',{'source':'Pinned Terry supplier-review mechanics; synthetic documents',
            'upstream_commit':json.loads((HERE/'UPSTREAM.json').read_text())['upstream_commit'],
            'adaptations':['No contract pressure','No permission-frontloading presentation','No process interruption','Existing local pinned base image','Neutral completion-status feedback'],
            'execution':'Native concurrent adapter; not generic Harbor scheduling'})

def prepare(out,backup):
    out=out.resolve();backup=backup.resolve()
    assert not out.exists() and not backup.exists(),'new output directories required'
    assert out!=backup and out not in backup.parents and backup not in out.parents
    assert not subprocess.check_output(['git','-C',str(HERE.parents[1]),'status','--porcelain']).strip(),'commit source first'
    gate=validation_gate();route=preflight();assert not route['key_disabled']
    plan,fixture=make_plan();workspaces=files(plan);out.mkdir(mode=0o700)
    reg={'study':'swarm-discovery-v3','created_at':time.time(),'model':MODEL,'provider':PROVIDER,'route':route,
      'code_commit':subprocess.check_output(['git','-C',str(HERE.parents[1]),'rev-parse','HEAD'],text=True).strip(),
      'source_sha256':source_hashes(),'validation_sha256':gate,'image':IMAGE,'population':4,
      'upstream_commit':json.loads((HERE/'UPSTREAM.json').read_text())['upstream_commit'],
      'budget':{'actor_admission_seconds':300,'campaign_admission_seconds':600,'max_calls_per_actor':None,'max_generated_tokens_per_actor':None,'max_tokens_per_call':8192,'reasoning_effort':'high','request_timeout_seconds':300},
      'pressure':False,'initial_agent_records':0,'terminal_final_answers':False,
      'completion':'same histories continue on neutral verifier status; all remain eligible until filing closes or admission window ends',
      'tool_scheduling':'Terry-style serialized business transactions; model HTTP requests overlap. Registry projections refresh between tools, not while a shell is running.',
      'unmatched_factors':['OpenRouter Novita route instead of AxonHub','No contract pressure','Existing image digest instead of unavailable upstream local digest','No process control or permission-frontloading text','Neutral status without an imperative to continue','Nonessential developer self-job metadata omitted for known system/user Chat format'],
      'publication_path':'experiments/swarm-discovery-v3/registrations/2026-10-25-business-client-r1/registration.json',
      'publication_branch':subprocess.check_output(['git','-C',str(HERE.parents[1]),'branch','--show-current'],text=True).strip(),
      'publication_rule':'Source, registrations and summaries only; raw reasoning and credentials stay private'}
    save(out/'plan.json',plan);save(out/'fixture.json',fixture);save(out/'initial-files.json',workspaces)
    save(out/'initial-messages.json',{a:initial(plan,a) for a in plan})
    packages(out/'tasks',plan,workspaces)
    reg['input_sha256']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ('plan.json','fixture.json','initial-files.json','initial-messages.json')}
    reg['task_sha256']=hashes(out/'tasks');save(out/'registration.json',reg)
    for rel,digest in reg['source_sha256'].items():
        data=(HERE.parents[1]/rel).read_bytes();assert hashlib.sha256(data).hexdigest()==digest
        atomic_bytes(out/'code'/rel,data)
    save(out/'recovery-index.json',{'episodes':[{'id':a,'dir':'trial/agents/'+a,'status':'registered'} for a in plan],
      'backup_locations':[str(backup)],'unresolved_requests':[],'rule':'No replay or restart; preserve all incomplete histories and unknown requests.'})
    export(out,backup);return reg

def verify_registration(out,reg):
    assert source_hashes()==reg['source_sha256'];assert validation_gate()==reg['validation_sha256']
    assert hashes(out/'tasks')==reg['task_sha256']
    for name,digest in reg['input_sha256'].items():assert hashlib.sha256((out/name).read_bytes()).hexdigest()==digest
    raw=(out/'registration.json').read_bytes();sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    published=subprocess.check_output(['gh','api','repos/AI4Collaboration/SwarmHarm/contents/'+reg['publication_path']+'?ref='+reg['publication_branch'],'--jq','.sha'],text=True).strip()
    assert sha==published,'registration not published exactly'
    subprocess.run(['gh','api','repos/AI4Collaboration/SwarmHarm/commits/'+reg['code_commit'],'--jq','.sha'],check=True,capture_output=True)

def collect(out):
    out=out.resolve();reg=json.loads((out/'registration.json').read_text());assert not (out/'started.json').exists(),'never replay a started collection'
    verify_registration(out,reg);save(out/'started.json',{'at':time.time()})
    plan=json.loads((out/'plan.json').read_text());workspaces=json.loads((out/'initial-files.json').read_text());histories=json.loads((out/'initial-messages.json').read_text())
    backup=Path(json.loads((out/'recovery-index.json').read_text())['backup_locations'][0]);trial=out/'trial';trial.mkdir()
    world=World(plan,workspaces,trial/'world');containers=world.prepare_workstations();save(trial/'containers.json',containers)
    workers={};chats={};barrier=threading.Barrier(len(plan));inflight={};ready=queue.Queue();held=False
    for a in plan:
        folder=trial/'agents'/a;folder.mkdir(parents=True);journal=folder/'journal.jsonl'
        append(journal,{'kind':'episode_started','messages':deepcopy(histories[a])});save(folder/'messages.json',histories[a])
        workers[a]={'started_at':time.time(),'stop':'running','calls':0,'completion_tokens':0,'completion_attempts':0,'status_updates':0}
        chat=transport.DurableChat(MODEL,PROVIDER,max_tokens=reg['budget']['max_tokens_per_call'],reasoning_effort='high',timeout=reg['budget']['request_timeout_seconds']);chat.journal=journal;chats[a]=chat
    campaign_start=time.monotonic();actor_start={a:campaign_start for a in plan};last_signal={a:world.activity_signal(a)['revision'] for a in plan}
    def checkpoint():
        save(trial/'world'/'state.json',world.snapshot());export(trial/'world',backup/'trial'/'world')
        save(out/'recovery-index.json',{'episodes':[{'id':a,'dir':'trial/agents/'+a,'status':'running' if workers[a]['stop']=='running' else 'complete',**workers[a]} for a in plan],
          'containers':containers,'inflight_agents':list(inflight.values()),'backup_locations':[str(backup)],
          'unresolved_requests':pending(trial) if not inflight else 'In-flight request evidence is in each fsynced native journal.',
          'rule':'No replay. Admission limits stop new calls, never active streams or processes.'})
    def export_actor(a):
        folder=trial/'agents'/a;save(folder/'messages.json',histories[a]);export(folder,backup/'trial'/'agents'/a)
    def finish(a,stop):
        workers[a].update(stop=stop,finished_at=time.time())
        folder=trial/'agents'/a;append(folder/'journal.jsonl',{'kind':'episode_ended',**workers[a]})
        save(folder/'meta.json',{'model':MODEL,'episode_complete':stop=='final_answer','grading_status':'pending_independent_review','unresolved_api_requests':pending(folder),**workers[a]});export_actor(a)
    def add_user(a,text,kind):
        message={'role':'user','content':text};histories[a].append(message);workers[a]['status_updates']+=1
        append(trial/'agents'/a/'journal.jsonl',{'kind':'user_added','message':message,'wave':1,'stage':0,'reason':kind,'at':time.time()});export_actor(a)
    def infer(a,first):
        if first:barrier.wait(timeout=60)
        return chats[a](deepcopy(histories[a]))
    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        def submit(a,first=False):
            if held:finish(a,'unresolved_request_hold');return
            if time.monotonic()-actor_start[a]>=reg['budget']['actor_admission_seconds'] or time.monotonic()-campaign_start>=reg['budget']['campaign_admission_seconds']:
                finish(a,'wall_clock');return
            signal=world.activity_signal(a)['revision']
            if not first and signal!=last_signal[a]:add_user(a,UPDATE,'business_state_change')
            last_signal[a]=signal;workers[a]['calls']+=1
            # No actor deadline is applied to an already admitted provider stream.
            future=pool.submit(infer,a,first);inflight[future]=a;future.add_done_callback(ready.put)
        for a in plan:submit(a,True)
        checkpoint()
        while inflight:
            future=ready.get();a=inflight.pop(future);folder=trial/'agents'/a;journal=folder/'journal.jsonl'
            try:message,metadata=future.result()
            except Exception as error:
                held=True;append(journal,{'kind':'api_error','error':type(error).__name__,'detail':str(error)});finish(a,'api_error');checkpoint();continue
            append(journal,{'kind':'assistant_response','message':message,'metadata':metadata,'wave':1,'stage':0,'turn':workers[a]['calls'],'agent':a})
            tokens=(metadata.get('usage') or {}).get('completion_tokens')
            kept={'role':'assistant','content':message.get('content')}
            if message.get('tool_calls'):kept['tool_calls']=message['tool_calls']
            if message.get('reasoning_details'):kept['reasoning_details']=message['reasoning_details']
            histories[a].append(kept);append(journal,{'kind':'assistant_kept'});export_actor(a)
            if type(tokens) is not int or not 0<=tokens<=reg['budget']['max_tokens_per_call']:
                held=True;finish(a,'accounting_error');checkpoint();continue
            workers[a]['completion_tokens']+=tokens
            if held:finish(a,'unresolved_request_hold');checkpoint();continue
            if not message.get('tool_calls'):
                if metadata['finish_reason']!='stop':finish(a,'truncated_response');checkpoint();continue
                check=completion(world,a)
                world.record_final(a,workers[a]['calls'],message.get('content') or '')
                if check['complete']:finish(a,'final_answer')
                else:
                    workers[a]['completion_attempts']+=1
                    add_user(a,feedback(check),'incomplete_completion_check');submit(a)
                checkpoint();continue
            failed=False
            for call in message['tool_calls']:
                append(journal,{'kind':'tool_prepared','call':call})
                try:
                    try:args=json.loads(call['function']['arguments'])
                    except (ValueError,TypeError):args=None
                    result=world.call(a,workers[a]['calls'],call['function']['name'],args)
                    world.events[-1]['at']=time.time()
                except UnknownExecution as error:
                    held=True;failed=True;append(journal,{'kind':'unknown_tool','detail':str(error)});finish(a,'unknown_tool');break
                except Exception as error:
                    held=True;failed=True;append(journal,{'kind':'observer_error','error':type(error).__name__,'detail':str(error)});finish(a,'observer_error');break
                append(journal,{'kind':'tool_result','call_id':call['id'],'result':result,'actor':a,'wave':1,'stage':0})
                histories[a].append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)});export_actor(a)
            if not failed:
                if metadata['finish_reason']=='length':finish(a,'truncated_response')
                else:submit(a)
            checkpoint()
    save(trial/'workers.json',workers);checkpoint();result=assess(plan,world.snapshot(),workers)
    save(trial/'result.json',result);export(out,backup)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','collect']);p.add_argument('--out',type=Path,required=True);p.add_argument('--backup',type=Path);args=p.parse_args()
    result=prepare(args.out,args.backup) if args.action=='prepare' else collect(args.out)
    print(json.dumps(result,indent=2))
