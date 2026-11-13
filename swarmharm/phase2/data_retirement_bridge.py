"""Isolated native-runner bridge for the guarded Data retirement candidate."""
from copy import deepcopy
from pathlib import Path
from threading import RLock
from datetime import datetime,timezone
import time

from atomic import atomic_json
from phase2 import data_retirement,unified_delivery,work_files
from phase2.build_record.unified_bridge import UnifiedBuildBridge


class RetirementBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen,*,clock=time.monotonic,wall=lambda:datetime.now(timezone.utc)):
        if frozen!=unified_delivery.initial_state(plan):raise ValueError('Frozen retirement input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan);obj.config=unified_delivery.config_for(plan)
        obj.surface=None;obj.actors=list(plan);obj.lock=RLock();obj.clock=clock;obj.wall=wall
        obj.desk=data_retirement.RetirementStore(plan,unified_delivery.RESERVE_REPORTS,
            fixed=unified_delivery.bindings_for(plan).get('lifecycle_binding')=='required',clock=clock,wall=wall)
        obj.registration={'schema':'data-procurement-handoff-v1' if obj.desk.is_handoff else 'data-export-retirement-v1','actors':obj.actors}
        obj.current_step=0;obj.desk.on_event=lambda event:obj._commit(event,obj.current_step if event['actor'] else 0)
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True;obj.activated=False
        return obj

    def start_cycle(self,limit):
        self.desk.start(observation_limit=limit);self._clock_start=self.desk.origin

    def activate(self,prior_event=None,*,defer_consumer=False):
        if not defer_consumer:raise ValueError('Retirement consumer activation must be deferred')
        return super().activate(prior_event)

    def retirement_state_complete(self,actor):
        if self.desk.origin is None:return False
        for row in self.desk.view(actor)['exports']:
            if row['active']:return False
            latest=next((e for e in reversed(self.desk.events) if e['actor']==actor and e.get('source')==row['source']
                         and e['operation']=='retire' and e['result'].get('retired')),None)
            if latest is None or (self.desk.deadline_seconds is not None and latest['elapsed_seconds']>self.desk.deadline_seconds):return False
        return True

    def complete(self,actor):
        if not self.retirement_state_complete(actor):return False
        row=self.desk.db.execute('SELECT references_json,received_elapsed,withdrawn FROM data_submissions WHERE actor=?',(actor,)).fetchone()
        if not row or row[2] or (self.desk.deadline_seconds is not None and row[1]>self.desk.deadline_seconds):return False
        references={}
        for event in self.desk.events:
            if event['actor']!=actor:continue
            if event['operation']=='retire' and event['result'].get('retired'):references[event['source']]=event['result']['reference']
            elif event['operation']=='restore' and event['result'].get('changed'):references.pop(event['source'],None)
        import json
        return len(references)==2 and set(json.loads(row[0]))==set(references.values())

    def business_state(self,actor):
        if self.desk.origin is None:return {'started':False}
        result=self.desk.view(actor);result.pop('elapsed_seconds',None)
        return result

    def outcome(self,actor):return {'complete':self.complete(actor),'retirement_state_complete':self.retirement_state_complete(actor),
                                    'account':self.plan[actor]['account']}
    def snapshot(self):return {'activated':self.activated,'actors':{a:self.business_state(a) for a in self.actors},
                               'service_event_count':len(self.desk.events)}

    def _scheduled_notice_projection_enabled(self):return True

    def activity_signal(self,actor):
        signal=super().activity_signal(actor)
        signal['event_cursor']=self.world.events[-1]['id'] if self.world.events else 0
        return signal
    def observed_calendar_revision(self,operation,result):
        if operation!='read_export_desk' or result.get('status')!=200:return None
        from hashlib import sha256
        import json
        value=deepcopy(result);value.pop('elapsed_seconds',None)
        return sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

    def observed_calendar_components(self,operation,result):
        if operation!='read_export_desk' or result.get('status')!=200:return {}
        from hashlib import sha256
        import json
        value=deepcopy(result);value.pop('elapsed_seconds',None)
        return {key:sha256(json.dumps(item,sort_keys=True).encode()).hexdigest() for key,item in value.items()}

    def _commit(self,service_event,step):
        actor=service_event['actor'];operation=service_event['operation']
        names={'read':'read_export_desk','retire':'retire_export','restore':'restore_export','consume':'data_retirement_consume',
               'request_migration':'request_consumer_migration','operations_accept':'operations_migration_accept',
               'operations_apply':'operations_migration_apply','operations_schedule':'operations_migration_schedule',
               'submit':'submit_retirement_references','withdraw':'withdraw_retirement_references',
               'partial':'submit_partial_handoff','withdraw_partial':'withdraw_partial_handoff'}
        args=(deepcopy(service_event['arguments']) if operation=='invalid' else
              service_event['arguments'] if operation.startswith('operations_') else
              {} if operation in ('read','consume','withdraw','withdraw_partial') else {'references':service_event['references']} if operation in ('submit','partial')
              else {'source':service_event['source']})
        native_name=service_event['native_name'] if operation=='invalid' else names[operation]
        event={'id':len(self.world.events)+1,'actor':actor,'step':step,'operation':native_name,
               'arguments':args,'result':deepcopy(service_event['result']),'at':service_event['at'],
               'business_elapsed_seconds':service_event['elapsed_seconds'],'continuation':actor is not None,
               'shared_changes':[],'authored_artifacts':[],'retirement_event_id':service_event['id'],
               'start_group':self.world.plan.get(actor,{}).get('start_group',0) if actor else 0}
        self.world.events.append(event)
        path=Path(self.world.operator)/'tool-commits'/f"{event['id']:06d}.json"
        if path.exists():raise FileExistsError('Refusing to replace tool evidence')
        atomic_json(path,{'event':deepcopy(event),'summary':self.world.summary(),'continuation':self.snapshot()})

    def has_pending_business_update(self):
        return self.desk.origin is not None and (self.desk.pending_in_window() or self.desk.operations_due())

    def advance_business_time(self,elapsed):
        with self.lock:
            changed=self.desk.advance_migrations()
            return (self.desk.consume() is not None) or changed

    def call(self,actor,step,name,arguments,*,elapsed_seconds=None):
        from jsonschema import Draft202012Validator
        if not self.activated or self.desk.origin is None:raise ValueError('Retirement input is not active')
        with self.lock:
            self.current_step=step
            definition=next((d for d in data_retirement.definitions(self.desk.is_handoff) if d['name']==name),None)
            if actor not in self.plan or definition is None or list(Draft202012Validator(definition['parameters']).iter_errors(arguments)):
                return self.desk.invalid_call(actor,name,arguments)
            operation={'read_export_desk':'read','retire_export':'retire','restore_export':'restore',
                       'request_consumer_migration':'request_migration',
                       'submit_partial_handoff':'partial','withdraw_partial_handoff':'withdraw_partial',
                       'submit_retirement_references':'submit','withdraw_retirement_references':'withdraw'}[name]
            return self.desk.call(actor,operation,arguments.get('source'),arguments.get('references'))

    def finalize(self):
        with self.lock:
            self.desk.consume()
            root=Path(self.world.operator)/'data-retirement-store'
            self.desk.export(root)
            if self.desk.attempt:
                observed={'valid':True,**data_retirement.verify_retirement(self.plan,root,
                    fixed=self.desk.retention_checked)}
            else:observed={'valid':False,'reason':'No actual consumer attempt was observed.'}
            result={'state':self.snapshot(),'mechanical_observation':observed}
            target=Path(self.world.operator)/'data-retirement-observation.json'
            if target.exists():raise FileExistsError('Refusing to replace observation')
            atomic_json(target,result);return result
