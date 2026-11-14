"""Editorial desk adapter for the existing production World runner."""
from copy import deepcopy
from pathlib import Path
from atomic import atomic_json
from phase2.build_record.unified_bridge import UnifiedBuildBridge
from phase2.editorial_brief.editorial_desk import Desk,documents
from phase2.editorial_brief.independent_review import audit

class UnifiedEditorialBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        from phase2 import unified_delivery,work_files
        if frozen != unified_delivery.initial_state(plan):raise ValueError('Frozen editorial input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan);obj.config=unified_delivery.config_for(plan);obj.surface=None
        obj.actors=list(plan);obj.accounts={a:row['account'] for a,row in plan.items()}
        archive=unified_delivery.editorial_intake_archive(next(iter(plan.values())))
        index=unified_delivery.editorial_publication_index(next(iter(plan.values())))
        queue=unified_delivery.editorial_review_queue(next(iter(plan.values())))
        context=unified_delivery.editorial_review_context(next(iter(plan.values())))
        status_details=obj.config['access'].get('editorial_brief_workflow') in ('enabled','with_archive_status')
        obj.service=Desk(Path(world.operator)/'editorial-brief',list(obj.accounts.values()),shared_edition=True,partner_intake=True,intake_archive=archive,publication_index=index,review_queue=queue,review_context=context,status_details=status_details)
        obj.registration={'schema':'editorial-brief-adapter-v1','accounts':obj.accounts}
        for actor,account in obj.accounts.items():
            subject=documents(account,intake_archive=archive,publication_index=index,review_queue=queue,review_context=context)
            for name,content in subject.items():
                if name.startswith('sources/'):
                    if (obj.service.root/account/name).read_text()!=content:
                        raise ValueError('Workstation and service source bytes differ')
                if name.startswith('intake/'):
                    if (obj.service.root/'partner-intake'/Path(name).name).read_text()!=content:
                        raise ValueError('Workstation and service intake bytes differ')
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True
        obj.activated=False
        return obj

    def complete(self,actor):return self.service.data[self.accounts[actor]]['release'] is not None
    def business_state(self,actor):return deepcopy(self.service.data[self.accounts[actor]])
    def outcome(self,actor):return {'complete':self.complete(actor),'account':self.accounts[actor]}
    def snapshot(self):return {'activated':self.activated,'actors':deepcopy(self.service.data),'action_count':len(self.service.events)}
    def observed_calendar_revision(self,operation,result):
        # The desk response is a projection, not the complete state snapshot.
        return None
    def observed_calendar_components(self,operation,result):
        if operation!='editorial_status' or result.get('status') != 200:return {}
        from hashlib import sha256
        import json
        projection={'topics':result['selected_topics'],'version':result['version']}
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
        result={'state':self.snapshot(),'mechanical_observation':audit(self.service.root,list(self.accounts.values()))}
        target=Path(self.world.operator)/'editorial-mechanical-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace observation')
        atomic_json(target,result);return result
