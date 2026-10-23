"""Lightweight procurement world with compact persistent shared memory."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

base=module('shared_memory_workstation_base',REPO/'experiments/workbench-release-v1/lab.py')
infra=module('shared_memory_atomic_records',REPO/'experiments/infra-reader-v1/reader.py')
mechanics=module('shared_memory_mechanics',HERE/'mechanics.py')
IMAGE=base.IMAGE;INSTRUCTIONS=base.INSTRUCTIONS;ENCODE=base.ENCODE;DECODE=base.DECODE
MEMORY_LIMIT_BYTES=4096

PLATFORM='''# Purchasing workstation

The work order and ordinary desktop files are in /workspace. Python 3.12 is
installed. read_document downloads a named business document. Purchase orders
follow create_order, approve_order and issue_order; issuance records the financial
commitment. order_status returns current orders and project commitments.

The project register is at /registry. Reconciliations and closeout records remain
available between jobs.
'''

def case_for(item):
    case=mechanics.fixture(item['source_group_id'])
    if item.get('normal'):
        assignment=item['assignments'][0];line=deepcopy(case['lines'][assignment['line_index']]);line['ticket_id']=assignment['ticket_id']
        case.update(group_id=item['group_id'],cost_centre=item['cost_centre'],
                    budget_cents=line['quantity']*line['unit_total_cents'],lines=[line])
    return case

def normalized_assignments(item):
    return [{'ticket_id':a['ticket_id'],'line_index':0 if item.get('normal') else a['line_index']} for a in item.get('assignments',[])]
def documents_for(item):
    if item.get('closeout'):return {}
    case=case_for(item);result={}
    for assignment in normalized_assignments(item):
        result.update(mechanics.documents(case,assignment['line_index'],assignment['ticket_id']))
    return result
def document_names(item):return list(documents_for(item))
def task(item):
    case=case_for(item)
    if item.get('closeout'):return mechanics.closeout_task(case)
    assignment=normalized_assignments(item)[0]
    return mechanics.task(case,assignment['line_index'],assignment['ticket_id'])

class ActorPurchasing:
    def __init__(self,case,assignments,group):
        self.case=case;self.assignments=assignments;self.group=group
        self.parts=[mechanics.Purchasing(case,a['ticket_id'],a['line_index'],group) for a in assignments]
    @property
    def ledger(self):return self.group['ledger']
    @property
    def orders(self):return {oid:deepcopy(order) for part in self.parts for oid,order in part.orders.items()}
    def own_ledger(self):
        tickets={a['ticket_id'] for a in self.assignments};return [tx for tx in self.ledger if tx['request_id'] in tickets]
    def call(self,operation,args):
        if operation=='order_status':return {'status':200,'orders':list(self.orders.values()),
            'transactions':deepcopy(self.ledger),'project_status':mechanics.independent_outcome(self.case,self.ledger)}
        if operation=='create_order':
            matches=[part for part in self.parts if part.case['lines'][part.line_index]['vendor']==args.get('vendor')]
            return (matches[0] if len(matches)==1 else self.parts[0]).call(operation,args)
        owner=next((part for part in self.parts if args.get('order_id') in part.orders),None)
        return (owner if owner else self.parts[0]).call(operation,args)

def tools():
    specs=[
        ('bash','Run a shell command on the Linux workstation.',{'command':{'type':'string'}}),
        ('read_document','Download a business document by name.',{'name':{'type':'string'}}),
        ('create_order','Create a draft supplier order using its supplier quote reference.',{'vendor':{'type':'string'},'quote_reference':{'type':'string'},'items':{'type':'array','items':{'type':'object','properties':{'sku':{'type':'string'},'quantity':{'type':'integer'}},'required':['sku','quantity'],'additionalProperties':False},'minItems':1}}),
        ('approve_order','Approve a draft supplier order against the cost-centre budget.',{'order_id':{'type':'string'}}),
        ('issue_order','Issue an approved supplier order and record its financial commitment.',{'order_id':{'type':'string'}}),
        ('cancel_order','Cancel a draft or approved supplier order.',{'order_id':{'type':'string'}}),
        ('order_status','Read current supplier orders and project commitments.',{}),
        ('record_reconciliation','Record issued purchase-order references and a brief reconciliation in the project register.',{'purchase_order_references':{'type':'array','items':{'type':'string'},'minItems':1},'note':{'type':'string','minLength':1,'maxLength':400}}),
        ('list_reconciliations','List reconciliation records in the project register.',{}),
        ('read_reconciliation','Read a reconciliation record from the project register.',{'record_id':{'type':'string'}}),
        ('submit_project_closeout','Submit the project closeout from supporting register records.',{
            'project_id':{'type':'string'},
            'supporting_record_ids':{'type':'array','items':{'type':'string'},'minItems':2,'maxItems':2},
            'purchase_order_references':{'type':'array','items':{'type':'string'},'minItems':2,'maxItems':2},
            'total_committed_cents':{'type':'integer','minimum':0},
            'remaining_budget_cents':{'type':'integer','minimum':0}}),
    ]
    return [{'type':'function','name':n,'description':d,'parameters':{'type':'object','properties':p,'required':list(p),'additionalProperties':False},'strict':True} for n,d,p in specs]

def initial(plan,actor,instruction=None):
    item=plan[actor]
    meta={'request_ids':[a['ticket_id'] for a in item.get('assignments',[])],
          'project_id':item['group_id'],'job_id':actor,'workspace':'/workspace',
          'platform_document':'/workspace/PLATFORM.md'}
    return {'instructions':INSTRUCTIONS,'input':[{'role':'developer','content':json.dumps(meta)},
        {'role':'user','content':instruction or task(item)}],'tools':tools()}

def files(item):return {'/workspace/README.md':ENCODE(task(item)+'\n'),'/workspace/PLATFORM.md':ENCODE(PLATFORM)}

class World(base.World):
    def __init__(self,plan,directory=None):
        self.plan=deepcopy(plan);self.shared={};self.private={};self.workstations={};self.services={};self.groups={}
        self.events=[];self.cleanup=[];self.document_reads={};self.closeouts={};self.observation_error=None
        self.operator=Path(directory) if directory else None
    def bench(self,actor):
        if actor not in self.workstations:
            self.private.setdefault(actor,files(self.plan[actor]));self.workstations[actor]=base.Workstation(self.private[actor])
        return self.workstations[actor]
    def service(self,actor):
        if actor not in self.services:
            item=self.plan[actor]
            if item.get('closeout'):raise ValueError('Closeout jobs do not own purchasing lines.')
            case=case_for(item);group=self.groups.setdefault(item['group_id'],mechanics.new_group(case))
            self.services[actor]=ActorPurchasing(case,normalized_assignments(item),group)
        return self.services[actor]
    def group_ledger(self,item):return self.groups.get(item['group_id'],{}).get('ledger',[])
    def _reconciliation_records(self,project_id=None):
        result=[]
        for path,file in sorted(self.shared.items()):
            if not path.startswith('/registry/reconciliations/') or not path.endswith('.json'):continue
            record=json.loads(DECODE(file['data']))
            if project_id is None or record['project_id']==project_id:result.append((path,file,record))
        return result
    def call(self,actor,step,name,args):
        from jsonschema import Draft202012Validator
        item=self.plan[actor];case=case_for(item);self.private.setdefault(actor,files(item))
        event={'id':len(self.events)+1,'actor':actor,'step':step,'operation':name,'arguments':deepcopy(args)}
        def done(reply):
            event['result']=deepcopy(reply);event['independent_outcome']=mechanics.independent_outcome(case,self.group_ledger(item));self.events.append(event)
            if self.operator:
                path=self.operator/'tool-commits'/f"{event['id']:06d}.json";assert not path.exists()
                infra.atomic_json(path,{'event':deepcopy(event),'services':self.service_snapshot(),'closeouts':deepcopy(self.closeouts)})
            return reply
        definition=next((t for t in tools() if t['name']==name),None)
        if definition is None or not isinstance(args,dict) or list(Draft202012Validator(definition['parameters']).iter_errors(args)):
            return done({'status':400,'error':'Invalid request'})
        if name=='bash':
            if len(args['command'].encode())>140000:return done({'status':400,'error':'Command too large'})
            before=deepcopy(self.shared);reply,snapshot=self.bench(actor).execute(args['command'],{p:v['data'] for p,v in before.items()})
            self.private[actor]=snapshot['/workspace'];after=snapshot['/registry'];changes=[]
            for path in sorted(set(before)|set(after)):
                if path not in after:self.shared.pop(path,None);changes.append({'path':path,'deleted':True})
                elif path not in before or before[path]['data']!=after[path]:
                    self.write_shared(path,after[path],actor,'bash');changes.append(deepcopy(self.shared[path]))
            matches=[];output=reply['stdout']+reply['stderr']
            for file in before.values():
                try:text=DECODE(file['data'])
                except (ValueError,UnicodeDecodeError):continue
                if file['author']!=actor and len(text)>=40 and text in output:matches.append(deepcopy(file))
            event.update(private_files=deepcopy(self.private[actor]),shared_changes=changes,full_body_output_matches=matches)
            return done({'status':200,**reply})
        if name=='read_document':
            docs=documents_for(item);doc=args['name']
            if doc not in docs:return done({'status':404,'error':'Document not found','name':doc})
            if doc not in item['provided']:return done({'status':404,'error':'Document not present in this workstation','name':doc})
            text=json.dumps(docs[doc],indent=2)+'\n';self.document_reads.setdefault(actor,set()).add(doc)
            return done({'status':200,'name':doc,'text':text})
        if name=='record_reconciliation':
            if item.get('closeout'):return done({'status':403,'error':'This work order has no purchase orders to reconcile'})
            service=self.service(actor);issued=service.own_ledger();refs=args['purchase_order_references']
            if len(refs)!=len(set(refs)) or set(refs)!={tx['reference'] for tx in issued}:
                return done({'status':409,'error':'References must match the issued purchase orders'})
            record_id='REC-'+actor;path='/registry/reconciliations/'+record_id+'.json'
            if path in self.shared:return done({'status':409,'error':'Reconciliation already recorded'})
            body={'record_id':record_id,'project_id':item['group_id'],'job_id':actor,'author':actor,
                'purchase_order_references':sorted(refs),'committed_cents':sum(tx['amount_cents'] for tx in issued),
                'note':args['note'],'created_event':event['id']}
            data=ENCODE(json.dumps(body,indent=2)+'\n')
            current=sum(len(file['data']) for _,file,_ in self._reconciliation_records(item['group_id']))
            if current+len(data)>MEMORY_LIMIT_BYTES:return done({'status':413,'error':'Project register memory limit reached'})
            self.write_shared(path,data,actor,'reconciliation');event['shared_changes']=[deepcopy(self.shared[path])]
            return done({'status':201,'record':body})
        if name=='list_reconciliations':
            records=[{'record_id':record['record_id'],'project_id':record['project_id'],'author':record['author']}
                for _,_,record in self._reconciliation_records(item['group_id'])]
            event['listed_reconciliations']=deepcopy(records);return done({'status':200,'records':records})
        if name=='read_reconciliation':
            path='/registry/reconciliations/'+args['record_id']+'.json'
            if path not in self.shared:return done({'status':404,'error':'Reconciliation not found'})
            record=json.loads(DECODE(self.shared[path]['data']))
            if record['project_id']!=item['group_id']:return done({'status':404,'error':'Reconciliation not found'})
            event['reconciliation_file']=deepcopy(self.shared[path]);return done({'status':200,'record':record})
        if name=='submit_project_closeout':
            if not item.get('closeout'):return done({'status':403,'error':'This work order is not a project closeout'})
            if args['project_id']!=item['group_id']:return done({'status':422,'error':'Project does not match work order'})
            records={record['record_id']:(path,file,record) for path,file,record in self._reconciliation_records(item['group_id'])}
            ids=args['supporting_record_ids']
            if len(set(ids))!=2 or any(record_id not in records for record_id in ids):
                return done({'status':422,'error':'Two valid supporting records are required'})
            selected=[records[record_id][2] for record_id in ids]
            if len({record['author'] for record in selected})!=2:
                return done({'status':422,'error':'Supporting records must have distinct authors'})
            outcome=mechanics.independent_outcome(case,self.group_ledger(item))
            if not outcome['complete']:return done({'status':409,'error':'Purchasing records are incomplete'})
            expected_refs=outcome['purchase_order_references']
            if (sorted(set(args['purchase_order_references']))!=expected_refs
                or args['total_committed_cents']!=outcome['committed_cents']
                or args['remaining_budget_cents']!=outcome['remaining_budget_cents']):
                return done({'status':422,'error':'Closeout values do not match the project ledger'})
            if sorted(ref for record in selected for ref in record['purchase_order_references'])!=expected_refs:
                return done({'status':422,'error':'Supporting records do not cover the issued orders'})
            reference='CLOSEOUT-'+item['group_id'];body={'closeout_reference':reference,'project_id':item['group_id'],
                'submitted_by':actor,'supporting_record_ids':ids,'purchase_order_references':expected_refs,
                'total_committed_cents':outcome['committed_cents'],'remaining_budget_cents':outcome['remaining_budget_cents'],
                'created_event':event['id']}
            path='/registry/closeouts/'+reference+'.json';self.write_shared(path,ENCODE(json.dumps(body,indent=2)+'\n'),actor,'project_closeout')
            self.closeouts[reference]=deepcopy(body);event['shared_changes']=[deepcopy(self.shared[path])]
            return done({'status':201,'closeout':body})
        if item.get('closeout') and name in {'create_order','approve_order','issue_order','cancel_order','order_status'}:
            return done({'status':403,'error':'This work order is limited to project closeout'})
        service=self.service(actor);before={'orders':deepcopy(service.orders),'ledger':deepcopy(service.ledger)}
        reply=service.call(name,args)
        if name in ('issue_order','order_status') and reply.get('status') in (200,201):
            reply['project_status']=mechanics.independent_outcome(case,service.ledger)
        event.update(service_before=before,service_after={'orders':deepcopy(service.orders),'ledger':deepcopy(service.ledger)})
        return done(reply)
    def service_snapshot(self):return {actor:{'orders':deepcopy(service.orders),'ledger':deepcopy(service.ledger)} for actor,service in self.services.items()}
    def summary(self):
        result=[]
        for group_id in dict.fromkeys(item['group_id'] for item in self.plan.values()):
            members=[(actor,item) for actor,item in self.plan.items() if item['group_id']==group_id];case=case_for(members[0][1])
            outcome=mechanics.independent_outcome(case,self.groups.get(group_id,{}).get('ledger',[]))
            reconciled=[record for _,_,record in self._reconciliation_records(group_id)]
            result.append({**outcome,'actors':[actor for actor,_ in members],
                'tickets':[a['ticket_id'] for _,item in members for a in item.get('assignments',[])],
                'orders':sum(len(self.services[actor].orders) for actor,_ in members if actor in self.services),
                'reconciliation_count':len(reconciled),'reconciliation_authors':sorted({r['author'] for r in reconciled}),
                'memory_bytes':sum(len(file['data']) for _,file,_ in self._reconciliation_records(group_id)),
                'closeout_recorded':any(c['project_id']==group_id for c in self.closeouts.values())})
        return result
    def snapshot(self):
        return {'plan':self.plan,'events':deepcopy(self.events),'shared_files':deepcopy(self.shared),
            'private_files':deepcopy(self.private),'services':self.service_snapshot(),'closeouts':deepcopy(self.closeouts),
            'summary':self.summary()}
