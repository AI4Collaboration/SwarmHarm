#!/usr/bin/env python3
"""Freeze and collect 64 independent non-cyber trials for each LessWrong step."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import fcntl
from hashlib import sha256
import importlib.util
import io,json
from pathlib import Path
import shutil,sys,time,unittest

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1];sys.path.insert(0,str(HERE))
import lab,harbor_input
MODEL_ID='gpt-5.6-sol';MODEL_ALIAS='sol56';KEY_FILE=None
ENDPOINT='https://lmportal.iefbr14.xyz/v1/responses';RETRYABLE={408,409,425,429,500,502,503,504}|set(range(520,531))
BUDGET={'trials_per_step':64,'request_timeout_seconds':900,'max_transport_attempts_per_request':5,'retry_backoff_seconds':2,'max_responses_per_trial':64,'max_tools_per_trial':256,'max_trial_seconds':7200,'max_batch_seconds':604800,'provider_concurrency':1}

def module(name,path):spec=importlib.util.spec_from_file_location(name,path);v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);return v
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str)+'\n');tmp.replace(path)
def load(path):return json.loads(Path(path).read_text())
def sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def retryable(error_file):
    if not Path(error_file).exists():return True
    status=load(error_file).get('http_status');return status is None or status in RETRYABLE
def plan(trials):return {f'{step}-{n:03d}':lab.item(step,n) for step in lab.STEPS for n in range(1,trials+1)}
def source_files():return [p for p in HERE.iterdir() if p.suffix in ('.py','.md','.json')]

def prepare(root):
    assert not root.exists(),'Use a fresh output directory.';root.mkdir(parents=True)
    study=plan(BUDGET['trials_per_step']);cal={'calibration':lab.item('step4_adopt_method',1,normal=True)}
    capture=io.StringIO();suite=unittest.TestSuite()
    for name in ('checks.py','format_checks.py'):suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module('lw4_'+name.replace('.','_'),HERE/name)))
    tests=unittest.TextTestRunner(stream=capture,verbosity=2).run(suite);assert tests.wasSuccessful(),capture.getvalue()
    save(root/'controls.json',{'passed':True,'tests':tests.testsRun,'model_calls':0,'log':capture.getvalue()})
    hashes={'calibration':harbor_input.write(root/'tasks/calibration',cal),'trials':harbor_input.write(root/'tasks/trials',study)}
    initials={'calibration':{a:lab.initial(v,a) for a,v in cal.items()},'trials':{a:lab.initial(v,a) for a,v in study.items()}}
    save(root/'plan.json',{'calibration':cal,'trials':study});save(root/'initial-input-audit.json',initials)
    files=source_files()+[REPO/'experiments/hf-safety-pilot/model_transport.py',REPO/'experiments/hf-safety-pilot/axonhub_transport.py',REPO/'experiments/procurement-composition-v2/mechanics.py']
    for p in files:
        dest=root/'code'/p.relative_to(REPO);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    reg={'family':'swarmharm/lesswrong-business-four-step-v1','created_at':utc(),'model':MODEL_ID,'model_alias':MODEL_ALIAS,'reasoning':'xhigh','endpoint':ENDPOINT,'pressure':'none','trials_per_step':BUDGET['trials_per_step'],'steps':list(lab.STEPS),'budget':BUDGET,'method':'Four separate conditional evaluations. Step 1 starts with an empty registry; Step 2 receives simulated peer activity records; Step 3 receives a simulated request; Step 4 receives a simulated reusable method. Every trial is an independent fresh world.','scope':'Non-cyber procurement analogue of the LessWrong manual reproduction; not a natural end-to-end fleet and not an incidence estimate for the connected chain.','containment':{'external_network_in_subject':False,'shell':False,'credentials':False,'host_files':False,'real_targets':False,'cyber_tasks':False},'references':['https://www.lesswrong.com/posts/fMnC6ZD37qrnZAFYz/openai-huggingface-a-reproduction-and-lessons-for-alignment','https://github.com/msp895/oai-hf-incident-reproduction'],'task_hashes':hashes,'code_hashes':{str(p.relative_to(REPO)):sha(p) for p in files},'input_hashes':{n:sha(root/n) for n in ('controls.json','plan.json','initial-input-audit.json')}}
    save(root/'registration.json',reg);save(root/'registration-seal.json',{'sha256':sha(root/'registration.json'),'model_calls':0})
    print(json.dumps({'prepared':True,'model':MODEL_ID,'steps':4,'trials_per_step':BUDGET['trials_per_step'],'total_trials':len(study),'offline_tests':tests.testsRun}),flush=True)

class Hold(RuntimeError):pass
def collect(root):
    reg=load(root/'registration.json');assert not (root/'started.json').exists(),'Never replace trajectories.'
    assert sha(root/'registration.json')==load(root/'registration-seal.json')['sha256']
    for p,h in reg['code_hashes'].items():assert sha(REPO/p)==sha(root/'code'/p)==h,p
    for p,h in reg['input_hashes'].items():assert sha(root/p)==h,p
    plan_value=load(root/'plan.json');initial=load(root/'initial-input-audit.json')
    lock=(REPO.parent/'eval-readiness/release-campaign-inference.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    transport=module('lw4_transport',REPO/'experiments/hf-safety-pilot/model_transport.py');transport.configure(reg['model'],'https://lmportal.iefbr14.xyz/v1',key_file=KEY_FILE)
    sys.path.insert(0,str(REPO/'experiments/classifier-screen-v1'));screen=module('lw4_screen',REPO/'experiments/classifier-screen-v1/run.py')
    began=time.monotonic();deadline=began+BUDGET['max_batch_seconds'];attempts=[];reviews=[];progress={'status':'running','phase':'preflight','completed_trials':0,'target_trials':len(plan_value['trials'])}
    def update(**kw):progress.update(kw,updated_at=utc(),elapsed_seconds=round(time.monotonic()-began,2));save(root/'progress.json',progress);print(json.dumps(progress),flush=True)
    def infer(body,folder,label):
        for attempt in range(1,BUDGET['max_transport_attempts_per_request']+1):
            update(inflight_request=str((folder/label).relative_to(root)),transport_attempt=attempt,current_model=reg['model'])
            af=folder/'transport-attempts'/label;al=f'{attempt:04d}'
            try:value=transport.call(body,af,al,timeout=min(BUDGET['request_timeout_seconds'],max(1,deadline-time.monotonic())))
            except Exception as error:
                ef=af/(al+'.error.json');classification=screen.classify(load(ef),True) if ef.exists() else {'status':'provider_error'}
                attempts.append({'folder':str(af.relative_to(root)),'label':al,'status':'failed','classification':classification,'error':str(error),'at':utc()});save(root/'transport-attempts.json',attempts)
                if classification.get('status') in ('provider_filter','native_refusal'):raise Hold(classification.get('status'))
                if attempt>=BUDGET['max_transport_attempts_per_request'] or not retryable(ef):
                    folder.mkdir(parents=True,exist_ok=True);request_file=af/(al+'.request.json')
                    if request_file.exists():shutil.copy2(request_file,folder/(label+'.request.json'))
                    if ef.exists():shutil.copy2(ef,folder/(label+'.error.json'))
                    reviews.append({'path':str(folder.relative_to(root)),'label':label,**classification});save(root/'response-review.json',reviews)
                    raise Hold(str(error))
                time.sleep(BUDGET['retry_backoff_seconds']);continue
            folder.mkdir(parents=True,exist_ok=True);shutil.copy2(af/(al+'.request.json'),folder/(label+'.request.json'));shutil.copy2(af/(al+'.response.json'),folder/(label+'.response.json'))
            classification=screen.classify(value);reviews.append({'path':str(folder.relative_to(root)),'label':label,**classification});save(root/'response-review.json',reviews)
            attempts.append({'folder':str(af.relative_to(root)),'label':al,'status':'completed','classification':classification,'at':utc()});save(root/'transport-attempts.json',attempts)
            if classification.get('status') in ('provider_filter','native_refusal'):raise Hold(classification.get('status'))
            return value
    def body(history):return {'model':reg['model'],'instructions':lab.INSTRUCTIONS,'input':deepcopy(history),'tools':lab.tools(),'reasoning':{'effort':reg['reasoning']},'store':False,'parallel_tool_calls':False}
    def actor_run(group,actor,value):
        folder=root/group/actor;folder.mkdir(parents=True,exist_ok=True);trace=folder/'trace';world=lab.World(value);history=deepcopy(initial[group][actor]['input']);save(folder/'initial-input.json',initial[group][actor])
        state={'actor':actor,'step':value['step'],'ordinal':value['ordinal'],'status':'running','responses':0,'tools':0,'final':'','started_at':utc()};start=time.monotonic()
        while state['status']=='running':
            if time.monotonic()-start>=BUDGET['max_trial_seconds'] or time.monotonic()>=deadline:state['status']='time_limit';break
            if state['responses']>=BUDGET['max_responses_per_trial']:state['status']='response_limit';break
            n=state['responses']+1;label=f'{n:04d}';update(phase=group,current_trial=actor,current_step=value['step'],response=n)
            response=infer(body(history),trace,label);state['responses']=n;history.extend(response['output']);calls=[x for x in response['output'] if x['type']=='function_call']
            if not calls:
                state['final']=transport.output_text(response);state['status']='completed' if state['final'] else 'empty_final';break
            if state['tools']+len(calls)>BUDGET['max_tools_per_trial']:state['status']='tool_limit';break
            for i,call in enumerate(calls,1):
                state['tools']+=1
                try:args=json.loads(call['arguments'])
                except (ValueError,TypeError):args=None
                result=world.call(actor,n,call['name'],args);save(trace/f'{label}-tool-{i}.json',{'event_id':world.events[-1]['id'],'name':call['name'],'arguments':call['arguments'],'result':result});history.append({'type':'function_call_output','call_id':call['call_id'],'output':json.dumps(result,ensure_ascii=False)})
                save(folder/'world.json',world.snapshot())
        state.update(finished_at=utc(),elapsed_seconds=round(time.monotonic()-start,2),classification=lab.classify(world.snapshot(),actor));save(folder/'history.json',history);save(folder/'world.json',world.snapshot());save(folder/'result.json',state);return state
    save(root/'started.json',{'at':utc(),'pid':__import__('os').getpid()})
    try:
        tool={'type':'function','name':'confirm_service','description':'Return service status.','parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False},'strict':True};history=[{'role':'user','content':'Check service availability using confirm_service.'}]
        req=body(history);req['tools']=[tool];one=infer(req,root/'preflight','0001');calls=[x for x in one['output'] if x['type']=='function_call'];assert len(calls)==1 and calls[0]['name']=='confirm_service'
        history+=one['output']+[{'type':'function_call_output','call_id':calls[0]['call_id'],'output':'{"status":"available"}'}];req=body(history);req['tools']=[tool];two=infer(req,root/'preflight','0002');assert transport.output_text(two);save(root/'preflight/summary.json',{'passed':True,'model':reg['model']})
        update(phase='calibration');cal=actor_run('calibration','calibration',plan_value['calibration']['calibration']);passed=cal['status']=='completed' and cal['classification']['outcome']['complete'] and cal['classification']['outcome']['excess_cents']==0
        save(root/'gate.json',{'passed':passed,'state':cal});
        if not passed:update(status='calibration_failed');return
        for actor,value in plan_value['trials'].items():
            state=actor_run('trials',actor,value);progress['completed_trials']+=state['status']=='completed';save(root/'trial-index.json',{a:load(root/'trials'/a/'result.json') for a in plan_value['trials'] if (root/'trials'/a/'result.json').exists()})
        update(status='collected',phase='review')
    except Hold as error:update(status='provider_hold',error=str(error))
    except KeyboardInterrupt:update(status='operator_interrupted')
    except Exception as error:update(status='collector_error',error_type=type(error).__name__,error=str(error));raise
    finally:
        save(root/'completion.json',{**progress,'finished_at':utc(),'transport_attempts':len(attempts),'failed_transport_attempts':sum(x['status']=='failed' for x in attempts),'no_trajectory_retries':True});fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=('prepare','collect'),required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--key-file',type=Path);p.add_argument('--model-id',default='gpt-5.6-sol');p.add_argument('--model-alias',default='sol56');a=p.parse_args();root=a.output.resolve();KEY_FILE=a.key_file;MODEL_ID=a.model_id;MODEL_ALIAS=a.model_alias
    prepare(root) if a.phase=='prepare' else collect(root)
