"""Connect the build target desk to the unified world runner."""
from copy import deepcopy
from pathlib import Path
from atomic import atomic_json
from phase2 import work_files
from phase2.build_record.target_adapter import TargetAdapter
from phase2.build_record.unified_bridge import UnifiedBuildBridge

class TargetBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        from phase2 import unified_delivery
        if frozen!=unified_delivery.initial_state(plan):raise ValueError('Frozen build target input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan);obj.config=unified_delivery.config_for(plan);obj.surface=None
        obj.actors=list(plan);accounts={actor:row['account'] for actor,row in plan.items()}
        root=Path(world.operator)/'build-target-service';obj.clarify_selection=unified_delivery.build_target_clarify_selection(next(iter(plan.values())))
        obj.fixture=unified_delivery.build_target_fixture(next(iter(plan.values())))
        obj.adapter=TargetAdapter(root,obj.actors,accounts=accounts,clarify_selection=obj.clarify_selection,fixture=obj.fixture)
        obj.registration={'schema':'build-target-production-adapter-v1','actors':obj.actors,'accounts':accounts,
            'private_files':{actor:unified_delivery.documents(row) for actor,row in plan.items()}}
        for actor,expected in obj.registration['private_files'].items():
            actual={path.name:path.read_text() for path in (root/actor).iterdir()
                    if path.is_file() and path.name!='build-record.json'}
            if actual!=expected:raise ValueError('Target service and workstation sources differ')
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True;obj.activated=False
        return obj

    def snapshot(self):
        return {'activated':self.activated,
                'actors':{actor:{**deepcopy(self.adapter.desk.actor_data[actor]),
                                 'selected_checks':deepcopy(self.adapter.desk.selected[actor]),
                                 **({'selection_revision':self.adapter.desk.revisions[actor]} if self.fixture else {})}
                          for actor in self.actors},
                'action_count':len(self.adapter.calls)}

    def finalize(self):
        from phase2.build_record.target_monitor import monitor
        observed=monitor(self.adapter.desk.root,self.actors,self.adapter.calls,accounts=self.registration['accounts'],clarify_selection=self.clarify_selection,fixture=self.fixture)
        result={'service_directory':'build-target-service','state':self.snapshot(),'mechanical_observation':observed}
        target=Path(self.world.operator)/'build-target-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace final observation')
        atomic_json(target,result);return result
