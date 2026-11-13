"""Connect the knowledge digest queue to the unified native event journal."""
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import json
from atomic import atomic_json
from phase2 import knowledge_digest_queue as q,work_files
from phase2.build_record.unified_bridge import UnifiedBuildBridge


class DigestBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        from phase2 import unified_delivery
        if frozen!=unified_delivery.initial_state(plan):raise ValueError('Frozen knowledge input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan)
        obj.config=unified_delivery.config_for(plan);obj.surface=None;obj.actors=list(plan)
        obj.accounts={actor:row['account'] for actor,row in plan.items()}
        obj.desk=q.Desk(Path(world.operator)/'knowledge-digest-service',obj.accounts,
                        fixed=unified_delivery.bindings_for(plan).get('lifecycle_binding','required')=='required')
        obj.current_step=0;obj.desk.on_event=lambda event:obj._commit(event,obj.current_step if event['actor'] is not None else 0)
        obj.registration={'schema':'knowledge-digest-adapter-v1','actors':obj.actors,'accounts':obj.accounts}
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True;obj.activated=False
        return obj

    def complete(self,actor):
        publication=self.desk.state[actor]['publication']
        return bool(publication and publication['published_elapsed']<=q.DEADLINE)
    def business_state(self,actor):return deepcopy(self.desk.state[actor])
    def outcome(self,actor):return {'complete':self.complete(actor),'account':self.accounts[actor]}
    def snapshot(self):return {'activated':self.activated,'actors':deepcopy(self.desk.state),'service_event_count':len(self.desk.events)}
    def observed_calendar_revision(self,operation,result):
        if operation!='read_knowledge_queue' or result.get('status')!=200:return None
        state={k:deepcopy(v) for k,v in result.items() if k not in ('status','publish_deadline_at','first_digest_window_at','next_digest_window_at','current_guide','launch_draft','subscription','edition_constraint')}
        return sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    def observed_calendar_components(self,operation,result):return {}
    def _commit(self,service_event,step):
        actor=service_event['actor'];event={'id':len(self.world.events)+1,'actor':actor,'step':step,
            'operation':service_event['operation'],'arguments':deepcopy(service_event['arguments']),
            'result':deepcopy(service_event['result']),'at':service_event['at'],
            'business_elapsed_seconds':service_event['elapsed_seconds'],'continuation':actor is not None,
            'shared_changes':[],'authored_artifacts':[],'digest_event_id':service_event['id'],
            'start_group':self.world.plan[actor].get('start_group',0) if actor is not None else 0}
        self.world.events.append(event);path=Path(self.world.operator)/'tool-commits'/f"{event['id']:06d}.json"
        if path.exists():raise FileExistsError('Refusing to replace tool evidence')
        atomic_json(path,{'event':deepcopy(event),'summary':self.world.summary(),'continuation':self.snapshot()})
    def configure_observation_limit(self,seconds):self.desk.set_limit(seconds)
    def start_digest_cycle(self,started_at):self.desk.start();self._clock_start=self.desk.started
    def has_pending_business_update(self):return self.desk.pending()
    def advance_business_time(self,elapsed):return bool(self.desk.advance())
    def call(self,actor,step,name,arguments,*,elapsed_seconds=None):
        if not self.activated:raise ValueError('The registered input is not active')
        with self.desk.lock:
            self.current_step=step
            return deepcopy(self.desk.call(actor,name,arguments)['result'])
    def finalize(self):
        from phase2.knowledge_digest_review import inspect
        if self.desk.started is None or self.desk.pending():observed={'valid':False,'reason':'Required digest windows did not occur before termination.'}
        else:
            self.desk.finish();observed=inspect(self.desk.root,self.accounts)
        target=Path(self.world.operator)/'knowledge-digest-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace observation')
        atomic_json(target,{'state':self.snapshot(),'mechanical_observation':observed})
