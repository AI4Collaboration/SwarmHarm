"""Connect the consolidation desk to the unified World event journal."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from atomic import atomic_json
from phase2 import work_files
from phase2.build_record.unified_bridge import UnifiedBuildBridge
from phase2.consolidation_adapter import Adapter, monitor
from phase2.consolidation_desk import metric_for, files_for


class ConsolidationBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        from phase2 import unified_delivery
        if frozen != unified_delivery.initial_state(plan):
            raise ValueError('Frozen consolidation input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan)
        obj.config=unified_delivery.config_for(plan);obj.surface=None
        obj.actors=list(plan)
        obj.metrics={actor:metric_for(row['account']) for actor,row in plan.items()}
        root=Path(world.operator)/'consolidation-service'
        fixed=unified_delivery.bindings_for(plan)['acceptance_binding']=='approved'
        obj.adapter=Adapter(root,obj.metrics,fixed=fixed)
        for actor,row in plan.items():
            files=unified_delivery.documents(row)
            if files!=files_for(row['account']) or json.loads(files['work-order.json'])!=obj.adapter.desk.orders[actor]:
                raise ValueError('Frozen workstation order differs')
            for name,content in files.items():
                if (name=='group-tree.json' or name.startswith('sources/')) and (root/name).read_text()!=content:
                    raise ValueError('Frozen workstation source differs from service')
        obj.registration={'schema':'consolidation-adapter-v1','actors':obj.actors,
                          'metrics':obj.metrics}
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True
        obj.activated=False
        return obj

    def complete(self,actor):return actor in self.adapter.desk.releases
    def business_state(self,actor):
        return self.adapter.desk.view_status(actor)
    def outcome(self,actor):return {'complete':self.complete(actor),'metric':self.metrics[actor]}
    def snapshot(self):
        return {'activated':self.activated,'orders':deepcopy(self.adapter.desk.orders),
                'templates':deepcopy(self.adapter.desk.templates),
                'releases':deepcopy(self.adapter.desk.releases),
                'action_count':len(self.adapter.calls)}
    def observed_calendar_revision(self,operation,result):
        if operation!='read_group_desk':return None
        return sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    def observed_calendar_components(self,operation,result):
        if operation!='read_group_desk':return {}
        return {key:sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
                for key,value in result.items()}
    def finalize(self):
        result={'state':self.snapshot(),
                'mechanical_observation':monitor(self.adapter.root,self.metrics,self.adapter.calls)}
        target=Path(self.world.operator)/'consolidation-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace final observation')
        atomic_json(target,result);return result
