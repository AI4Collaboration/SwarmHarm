"""Activity desk adapter for the existing production World runner."""
from copy import deepcopy
from pathlib import Path
from atomic import atomic_json
from phase2.build_record.unified_bridge import UnifiedBuildBridge
from phase2.activity_report.activity_desk import Desk,documents
from phase2.activity_report.independent_review import audit

class UnifiedActivityBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        from phase2 import unified_delivery,work_files
        if frozen != unified_delivery.initial_state(plan):raise ValueError('Frozen activity input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan);obj.config=unified_delivery.config_for(plan);obj.surface=None
        obj.actors=list(plan);obj.accounts={a:row['account'] for a,row in plan.items()}
        obj.progressive=unified_delivery.activity_report_progressive(next(iter(plan.values())))
        obj.service=Desk(Path(world.operator)/'activity-report',list(obj.accounts.values()),progressive=obj.progressive)
        obj.registration={'schema':'activity-report-adapter-v1','accounts':obj.accounts}
        for actor,account in obj.accounts.items():
            subject=documents(account,progressive=obj.progressive)
            for name,content in subject.items():
                if name.startswith('activity-') and name.endswith('.csv'):
                    day=name.removeprefix('activity-').removesuffix('.csv')
                    if (obj.service.root/account/'sources'/f'{day}.csv').read_text()!=content:
                        raise ValueError('Workstation and service source bytes differ')
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True
        obj.activated=False
        return obj

    def complete(self,actor):return self.service.data[self.accounts[actor]]['release'] is not None
    def business_state(self,actor):
        return {**deepcopy(self.service.data[self.accounts[actor]]),'publications':self.service.publications()}
    def outcome(self,actor):return {'complete':self.complete(actor),'account':self.accounts[actor]}
    def snapshot(self):return {'activated':self.activated,'actors':deepcopy(self.service.data),'action_count':len(self.service.events)}
    def observed_calendar_revision(self,operation,result):
        # The desk response is a projection, not the complete state snapshot.
        return None
    def observed_calendar_components(self,operation,result):
        if operation not in ('desk_status','list_published_reports') or result.get('status') != 200:return {}
        from hashlib import sha256
        import json
        projection=({'dates':result['selected_dates'],'version':result['version'],'used':result['used']}
                    if operation=='desk_status' else {'publications':result['reports']})
        if operation=='desk_status' and 'processed_days' in result:
            projection['processed_days']=result['processed_days']
        return {key:sha256(json.dumps(value,sort_keys=True).encode()).hexdigest() for key,value in projection.items()}
    def call(self,actor,step,name,arguments,*,elapsed_seconds=None):
        if not self.activated:raise ValueError('The registered input is not active')
        result=self.service.call(self.accounts[actor],name,arguments)
        event={'id':len(self.world.events)+1,'actor':actor,'step':step,'operation':name,
               'arguments':deepcopy(arguments),'result':deepcopy(result),'continuation':True,
               'shared_changes':[],'authored_artifacts':[],'service_event_id':len(self.service.events),
               'start_group':self.world.plan[actor].get('start_group',0)}
        self.world.events.append(event);target=Path(self.world.operator)/'tool-commits'/f"{event['id']:06d}.json"
        if target.exists():raise ValueError('Refusing to replace evidence')
        atomic_json(target,{'event':deepcopy(event),'summary':self.world.summary(),'continuation':self.snapshot()})
        return result
    def finalize(self):
        result={'state':self.snapshot(),'mechanical_observation':audit(self.service.root,list(self.accounts.values()),progressive=self.progressive)}
        target=Path(self.world.operator)/'activity-mechanical-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace observation')
        atomic_json(target,result);return result
