"""Connect the client activity desk to the unified event journal."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from atomic import atomic_json
from phase2 import data_identity,work_files
from phase2.build_record.unified_bridge import UnifiedBuildBridge


class IdentityBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        from phase2 import unified_delivery
        if frozen!=unified_delivery.initial_state(plan):raise ValueError('Frozen identity input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan);obj.config=unified_delivery.config_for(plan)
        obj.surface=None;obj.actors=list(plan);obj.accounts={a:r['account'] for a,r in plan.items()}
        obj.adapter=data_identity.Desk(Path(world.operator)/'data-identity-service',obj.accounts,
                                     fixed=unified_delivery.bindings_for(plan)['acceptance_binding']=='approved')
        for actor,row in plan.items():
            if unified_delivery.documents(row)!=data_identity.documents(row['account']):raise ValueError('Frozen documents differ')
            if json.loads((obj.adapter.root/'sources'/f"{row['account']}.json").read_text())!=data_identity.source(row['account']):
                raise ValueError('Frozen source differs')
        obj.registration={'schema':'data-identity-adapter-v1','actors':obj.actors,'accounts':obj.accounts}
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True;obj.activated=False
        return obj

    def complete(self,actor):
        row=self.adapter.releases.get((actor,'final'))
        return bool(row and row['actual_metric']==row['requested_metric'] and row['status']=='calculated')
    def business_state(self,actor):return self.adapter.status(actor)
    def outcome(self,actor):return {'complete':self.complete(actor),'account':self.accounts[actor]}
    def snapshot(self):
        return {'activated':self.activated,'views':deepcopy(self.adapter.views),
                'mapping_versions':deepcopy(self.adapter.versions),'releases':[deepcopy(row) for _,row in sorted(self.adapter.releases.items())],
                'action_count':len(self.adapter.calls)}
    def observed_calendar_revision(self,operation,result):
        if operation!='read_activity_desk':return None
        return sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    def observed_calendar_components(self,operation,result):
        if operation!='read_activity_desk':return {}
        return {key:sha256(json.dumps(value,sort_keys=True).encode()).hexdigest() for key,value in result.items()}
    def finalize(self):
        result={'state':self.snapshot(),'mechanical_observation':data_identity.monitor(self.adapter.root,self.accounts,self.adapter.calls)}
        target=Path(self.world.operator)/'data-identity-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace final observation')
        atomic_json(target,result);return result
