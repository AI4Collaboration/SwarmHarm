"""Connect the foreign-currency expense desk to the unified event journal."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from atomic import atomic_json
from phase2 import finance_fx,work_files
from phase2.build_record.unified_bridge import UnifiedBuildBridge


class FxBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls,world,plan,frozen):
        from phase2 import unified_delivery
        if frozen!=unified_delivery.initial_state(plan):raise ValueError('Frozen foreign exchange input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan);obj.config=unified_delivery.config_for(plan)
        obj.surface=None;obj.actors=list(plan);obj.accounts={a:r['account'] for a,r in plan.items()}
        obj.adapter=finance_fx.Desk(Path(world.operator)/'finance-fx-service',obj.accounts,
                                     fixed=unified_delivery.bindings_for(plan)['acceptance_binding']=='approved')
        for actor,row in plan.items():
            if unified_delivery.documents(row)!=finance_fx.documents(row['account']):raise ValueError('Frozen documents differ')
            if json.loads((obj.adapter.root/'sources'/f"{row['account']}.json").read_text())!=finance_fx.source(row['account']):
                raise ValueError('Frozen source differs')
        obj.registration={'schema':'finance-fx-adapter-v1','actors':obj.actors,'accounts':obj.accounts}
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
                'rates_versions':deepcopy(self.adapter.versions),'releases':[deepcopy(row) for _,row in sorted(self.adapter.releases.items())],
                'action_count':len(self.adapter.calls)}
    def observed_calendar_revision(self,operation,result):
        if operation!='read_fx_desk':return None
        return sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    def observed_calendar_components(self,operation,result):
        if operation!='read_fx_desk':return {}
        return {key:sha256(json.dumps(value,sort_keys=True).encode()).hexdigest() for key,value in result.items()}
    def finalize(self):
        result={'state':self.snapshot(),'mechanical_observation':finance_fx.monitor(self.adapter.root,self.accounts,self.adapter.calls)}
        target=Path(self.world.operator)/'finance-fx-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace final observation')
        atomic_json(target,result);return result
