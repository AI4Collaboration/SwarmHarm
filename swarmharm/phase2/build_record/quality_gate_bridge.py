"""Isolated native world adapter; this candidate is not registrable."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from atomic import atomic_json
from phase2 import unified_delivery,work_files
from phase2.build_record import quality_gate,quality_gate_monitor
from phase2.build_record.unified_bridge import UnifiedBuildBridge


class QualityGateBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        if frozen!=unified_delivery.initial_state(plan):raise ValueError('Frozen quality-gate input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan);obj.config=unified_delivery.config_for(plan)
        obj.surface=None;obj.actors=list(plan);accounts={a:r['account'] for a,r in plan.items()}
        original_binding=unified_delivery.bindings_for(plan)['grader_binding']=='installed'
        obj.adapter=quality_gate.Adapter(Path(world.operator)/'quality-gate-service',obj.actors,accounts=accounts,original_binding=original_binding)
        obj.registration={'schema':'quality-gate-candidate-v1','actors':obj.actors,'accounts':accounts}
        for actor,row in plan.items():
            expected=quality_gate.documents(row['account'])
            actual={p.name:p.read_text() for p in (obj.adapter.desk.root/actor).iterdir()
                    if p.is_file() and p.name!='build-record.json'}
            if unified_delivery.documents(row)!=expected or actual!=expected:
                raise ValueError('Frozen quality-gate workstation input differs')
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True;obj.activated=False
        return obj

    def snapshot(self):
        return {'activated':self.activated,'actors':deepcopy(self.adapter.desk.actor_data),
                'quality_versions':deepcopy(self.adapter.desk.quality_versions),'action_count':len(self.adapter.calls)}

    def complete(self,actor):
        desk=self.adapter.desk
        return bool(desk.actor_data[actor]['release'] is not None and
                    all(desk._receipt_valid(actor,check) for check in quality_gate.GATED))

    def outcome(self,actor):
        return {'complete':self.complete(actor),'published':self.adapter.desk.actor_data[actor]['release'] is not None,
                'account':self.registration['accounts'][actor]}

    def observed_calendar_revision(self,operation,result):
        if operation!='read_quality_desk':return None
        return sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()

    def observed_calendar_components(self,operation,result):
        if operation!='read_quality_desk':return {}
        return {k:sha256(json.dumps(v,sort_keys=True).encode()).hexdigest() for k,v in result.items()}

    def finalize(self):
        hashes=quality_gate.file_hashes(self.adapter.desk.root)
        observation=quality_gate_monitor.monitor(self.adapter.desk.root,self.registration['accounts'],self.adapter.calls,sealed_hashes=hashes,
                                                 original_binding=self.adapter.desk.original_binding)
        target=Path(self.world.operator)/'quality-gate-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace final observation')
        result={'state':self.snapshot(),'sealed_files':hashes,'mechanical_observation':observation}
        atomic_json(target,result);return result
