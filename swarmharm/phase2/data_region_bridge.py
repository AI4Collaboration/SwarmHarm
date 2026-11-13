"""Connect the regional reporting desk to the unified event journal."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from atomic import atomic_json
from phase2 import data_region,work_files
from phase2.build_record.unified_bridge import UnifiedBuildBridge


class RegionBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        from phase2 import unified_delivery
        if frozen!=unified_delivery.initial_state(plan):raise ValueError('Frozen region input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan);obj.config=unified_delivery.config_for(plan)
        obj.surface=None;obj.actors=list(plan);obj.accounts={a:r['account'] for a,r in plan.items()}
        obj.adapter=data_region.Desk(Path(world.operator)/'data-region-service',obj.accounts,
                                     fixed=unified_delivery.bindings_for(plan)['acceptance_binding']=='approved')
        for actor,row in plan.items():
            if unified_delivery.documents(row)!=data_region.documents(row['account']):raise ValueError('Frozen documents differ')
            if (obj.adapter.root/'sources'/f"{row['account']}.csv").read_text()!=data_region.source_csv(row['account']):
                raise ValueError('Frozen source differs')
        obj.registration={'schema':'data-region-adapter-v1','actors':obj.actors,'accounts':obj.accounts}
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True;obj.activated=False
        return obj

    def complete(self,actor):return actor in self.adapter.releases
    def business_state(self,actor):return self.adapter.status(actor)
    def outcome(self,actor):return {'complete':self.complete(actor),'account':self.accounts[actor]}
    def snapshot(self):
        return {'activated':self.activated,'views':deepcopy(self.adapter.views),
                'dimension_version':self.adapter.dimension_version,'releases':deepcopy(self.adapter.releases),
                'action_count':len(self.adapter.calls)}
    def observed_calendar_revision(self,operation,result):
        if operation!='read_region_desk':return None
        return sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    def observed_calendar_components(self,operation,result):
        if operation!='read_region_desk':return {}
        return {key:sha256(json.dumps(value,sort_keys=True).encode()).hexdigest() for key,value in result.items()}
    def finalize(self):
        result={'state':self.snapshot(),'mechanical_observation':data_region.monitor(self.adapter.root,self.accounts,self.adapter.calls)}
        target=Path(self.world.operator)/'data-region-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace final observation')
        atomic_json(target,result);return result
