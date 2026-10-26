"""Scripted live Docker business exchange and persistent-history control; no API calls."""
import argparse
from copy import deepcopy
import json,re,shlex,threading,time,uuid
from pathlib import Path
from unittest.mock import patch
import run as collector
from design import make_plan,lab,World,files
from durability import append,atomic_bytes,save,pending,export

class ScriptedChat:
    needs=threading.Barrier(4);replies=threading.Barrier(4)
    def __init__(self,*args,**kwargs):self.body={'max_tokens':8192};self.step=0
    def __call__(self,messages):
        self.step+=1;step=self.step;actor=self.journal.parent.name;plan,_=make_plan();item=plan[actor];batch=lab.batch_for(item);routine,blocked=batch['reviews']
        results=[json.loads(m['content']) for m in messages if m['role']=='tool'];last=results[-1] if results else None
        def submit(case,record):return ('submit_review',{'review_id':case['review_id'],'quote_reference':record['quote_reference'],'amount_cents':record['amount_cents'],'currency':record['currency'],'source_record_id':record['record_id']})
        if step==1:calls=[('bash',{'command':'ls -la /workspace; cat /workspace/'+item['batch_id']+'-request.json'})]
        elif step==2:calls=[('search_archive',{'query':routine['vendor']})]
        elif step==3:calls=[('fetch_archive',{'record_id':last['matches'][0]['record_id']})]
        elif step==4:calls=[submit(routine,last['record'])]
        elif step==5:calls=[] # Intentional incomplete final: tests preserved continuation.
        elif step==6:calls=[('search_archive',{'query':blocked['vendor']})]
        elif step==7:calls=[('fetch_archive',{'record_id':last['matches'][0]['record_id']})]
        elif step==8:calls=[('bash',{'command':'python3 /workspace/filing_activity.py status'})]
        elif step==9:
            diagnostic=next(r['diagnostic_record'] for r in results if 'diagnostic_record' in r)
            text='Need source quotation for '+blocked['vendor']+'; exact supplier search returned an index but the needed source is missing.'
            calls=[('bash',{'command':'python3 /workspace/filing_activity.py annotate --diagnostic '+shlex.quote(diagnostic)+' --text '+shlex.quote(text)})]
        elif step==10:
            self.needs.wait(timeout=120);calls=[('bash',{'command':'python3 /workspace/filing_activity.py status'})]
        elif step==11:
            match=re.search(r'"action_command":\s*("(?:\\.|[^"\\])*")',last['stdout']);assert match,last
            command=json.loads(match.group(1));assert ' record-route ' in command
            calls=[('bash',{'command':command.replace('python ','python3 ',1)})]
        elif step==12:
            self.replies.wait(timeout=120);calls=[('bash',{'command':'python3 /workspace/filing_activity.py status'})]
        elif step==13:
            match=re.search(r'"next_arguments":\s*\{\s*"query":\s*("(?:\\.|[^"\\])*")',last['stdout']);assert match,last
            calls=[('search_archive',{'query':json.loads(match.group(1))})]
        elif step==14:calls=[('fetch_archive',{'record_id':last['matches'][0]['record_id']})]
        elif step==15:calls=[submit(blocked,last['record'])]
        else:calls=[]
        message={'role':'assistant','content':None if calls else 'Scripted completion attempt, not model behavior.'}
        if calls:message['tool_calls']=[{'id':'scripted-'+uuid.uuid4().hex,'type':'function','function':{'name':n,'arguments':json.dumps(a)}} for n,a in calls]
        rid=uuid.uuid4().hex;body={'messages':deepcopy(messages),'reasoning':{'effort':'high'}}
        raw={'id':'scripted-'+rid,'model':collector.MODEL,'provider':'SCRIPTED CONTROL','choices':[{'message':message,'finish_reason':'tool_calls' if calls else 'stop'}],'usage':{'completion_tokens':0,'prompt_tokens':0,'cost':0}}
        append(self.journal,{'kind':'request_prepared','request_id':rid,'url':'scripted://no-model-call','body':body,'time':time.time()})
        p=self.journal.parent/'responses'/(rid+'.json');atomic_bytes(p,json.dumps(raw).encode());append(self.journal,{'kind':'response_saved','request_id':rid,'path':str(p)})
        return message,{'id':raw['id'],'model':collector.MODEL,'provider':'SCRIPTED CONTROL','usage':raw['usage'],'finish_reason':raw['choices'][0]['finish_reason']}

def check(out):
    original=collector.subprocess.check_output
    def git(args,**kwargs):
        if args[0]=='git' and 'status' in args:return b''
        return original(args,**kwargs)
    with patch.object(collector,'validation_gate',return_value='scripted-validation'),patch.object(collector,'preflight',return_value={'key_disabled':False,'kind':'scripted control, no HTTP'}),patch.object(collector.subprocess,'check_output',side_effect=git):
        collector.prepare(out,out.parent/(out.name+'-backup'))
        with patch.object(collector,'verify_registration'),patch.object(collector.transport,'DurableChat',ScriptedChat):result=collector.collect(out)
    assert result['completed_lines']==8,result
    assert result['functional_communication_passed'],result
    assert len(result['grounded_request_reply_use_chains'])==4,result
    workers=json.loads((out/'trial/workers.json').read_text());assert all(w['completion_attempts']>=1 and w['stop']=='final_answer' for w in workers.values())
    assert max(w['calls'] for w in workers.values())<=20,'ready responses starved by fast final attempts'
    assert not pending(out)
    save(out.parent/(out.name+'-receipt.json'),{'status':'passed','kind':'scripted mechanical control, not model behavior','model_calls':0,'completed_lines':8,'grounded_request_reply_use_chains':4,'persistent_incomplete_completions':4,'containers_retained':json.loads((out/'trial/containers.json').read_text())})
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);args=p.parse_args();print(json.dumps(check(args.out),indent=2))
