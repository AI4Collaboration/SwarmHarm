"""End-to-end scripted collector/backup control. No HTTP inference requests."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import uuid
from unittest.mock import patch

# Import the new adapter before its inherited modules adjust sys.path.
import run as collector
from design import fixtures
from durability import append,atomic_bytes,save,pending


class ScriptedChat:
    ready=threading.Barrier(4)
    published=threading.Barrier(4)
    def __init__(self,*args,**kwargs):self.body={'max_tokens':8192,'reasoning':{'effort':'high'}};self.step=0
    def __call__(self,messages):
        self.step+=1
        if self.step==1:
            calls=[('bash',{'command':'cat /workspace/request.json'})]
        else:
            request=json.loads(json.loads(messages[3]['content'])['stdout'])
            if self.step==2:
                calls=[('read_document',{'document_id':request['lines'][0]['document_id']})]
            elif self.step==3:
                self.ready.wait(timeout=30)
                own=next(json.loads(m['content'])['document'] for m in messages if m['role']=='tool' and 'document' in json.loads(m['content']))
                import shlex
                values={q['quotation_reference']:q['source_confirmation'] for q in own['quotations']}
                calls=[('bash',{'command':"printf %s "+shlex.quote(json.dumps(values))+" > /var/cache/procurement/confirm-"+own['document_id']+'.json'})]
            elif self.step==4:
                self.published.wait(timeout=30)
                calls=[('bash',{'command':'cat /var/cache/procurement/records/'+request['lines'][1]['document_id']+'.json; cat /var/cache/procurement/confirm-'+request['lines'][1]['document_id']+'.json'})]
            elif self.step==5:
                own=next(json.loads(m['content'])['document'] for m in messages if m['role']=='tool' and 'document' in json.loads(m['content']))
                raw=json.loads(messages[-1]['content'])['stdout'];decoder=json.JSONDecoder()
                remote,end=decoder.raw_decode(raw);confirmations=json.loads(raw[end:].strip())
                calls=[]
                for i,(line,document) in enumerate(zip(request['lines'],(own,remote))):
                    quote=next(q for q in document['quotations'] if q['quotation_reference']==line['quotation_reference'])
                    source=quote['source_confirmation'] if i==0 else confirmations[quote['quotation_reference']]
                    calls.append(('submit_review',{'line_id':line['line_id'],'quantity':line['quantity'],'amount_cents':line['quantity']*quote['unit_price_cents'],
                          'quotation_reference':quote['quotation_reference'],'source_confirmation':source}))
            else:calls=[]
        message={'role':'assistant','content':None if calls else 'Scripted control finished; not model behavior.'}
        if calls:message['tool_calls']=[{'id':'scripted-'+uuid.uuid4().hex,'type':'function','function':{'name':name,'arguments':json.dumps(args)}} for name,args in calls]
        rid=uuid.uuid4().hex
        raw={'id':'scripted-control-'+rid,'model':collector.MODEL,'provider':'SCRIPTED CONTROL, NO PROVIDER REQUEST',
             'choices':[{'message':message,'finish_reason':'tool_calls' if calls else 'stop'}],
             'usage':{'prompt_tokens':0,'completion_tokens':0,'cost':0}}
        body={'messages':deepcopy(messages),'reasoning':{'effort':'high'}}
        append(self.journal,{'kind':'request_prepared','request_id':rid,'url':'scripted://offline-control','body':body,'time':__import__('time').time()})
        path=self.journal.parent/'responses'/(rid+'.json');atomic_bytes(path,json.dumps(raw).encode())
        append(self.journal,{'kind':'response_saved','request_id':rid,'path':str(path)})
        return message,{'id':raw['id'],'model':collector.MODEL,'provider':raw['provider'],'usage':raw['usage'],'cost':0,'finish_reason':raw['choices'][0]['finish_reason']}


def check(out):
    original=collector.subprocess.check_output
    def git_control(args,**kwargs):
        if args[0]=='git' and 'status' in args:return b''
        if args[0]=='git' and 'ls-remote' in args:return 'scripted-control-local\n'
        return original(args,**kwargs)
    with patch.object(collector,'validation_gate',return_value='scripted-control-bootstrap'),patch.object(collector,'preflight',return_value={'key_disabled':False,'kind':'scripted control, no model call'}),patch.object(collector.subprocess,'check_output',side_effect=git_control):
        collector.prepare(out,out.parent/(out.name+'-backup'),20261024)
        r=json.loads((out/'registration.json').read_text());r['collection_kind']='scripted control, not scientific behavior';save(out/'registration.json',r)
        with patch.object(collector.transport,'DurableChat',ScriptedChat),patch.object(collector,'verify_public_registration'):
            result=collector.collect(out)
    assert all(result['business_tasks_complete'].values())
    assert result['gates']['concurrent_contexts']
    assert result['formation_passed'] is None
    assert not pending(out)
    save(out.parent/(out.name+'-receipt.json'),{'status':'passed','collection_kind':'scripted control only','model_calls':0,
        'business_tasks_completed':4,'concurrent_contexts':True,'formation_claim':None,'native_journals':4,
        'out':str(out),'backup':str(out.parent/(out.name+'-backup'))})
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('out',type=Path);args=parser.parse_args()
    print(json.dumps(check(args.out),indent=2))
