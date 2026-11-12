"""Connect the build-check desk to the unified runner and event journal."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from atomic import atomic_json
from phase2 import work_files
from phase2.build_record.harness_adapter import HarnessAdapter


class UnifiedBuildBridge:
    continuous_workflow=True
    acknowledge_authored_calendar_changes=True

    @classmethod
    def from_plan(cls, world, plan, frozen):
        from phase2 import unified_delivery
        if frozen != unified_delivery.initial_state(plan):raise ValueError('Frozen build input differs')
        obj=cls.__new__(cls);obj.world=world;obj.plan=deepcopy(plan)
        obj.config=unified_delivery.config_for(plan);obj.surface=None
        obj.actors=list(plan)
        accounts={actor:row['account'] for actor,row in plan.items()}
        service_root=Path(world.operator)/'build-check-service'
        obj.receipt_defined=obj.config['access'].get('build_record_workflow')=='receipt-defined'
        obj.adapter=HarnessAdapter(service_root,obj.actors,accounts=accounts,receipt_defined=obj.receipt_defined)
        obj.registration={'schema':'build-record-production-adapter-v1','actors':obj.actors,'accounts':accounts,
            'private_files':{actor:unified_delivery.documents(row) for actor,row in plan.items()}}
        for actor,expected in obj.registration['private_files'].items():
            actual={path.name:path.read_text() for path in (service_root/actor).iterdir()
                    if path.is_file() and path.name!='build-record.json'}
            if actual!=expected:raise ValueError('Service input differs from frozen workstation input')
        world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
        world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        world.shared_record_visibility=lambda actor,row:True
        obj.activated=False
        return obj

    def open_library_link(self):return None

    def activate(self, prior_event=None):
        if prior_event is not None or self.activated or self.world.events:raise ValueError('Activation requires an empty world')
        self.activated=True
        return {'study_track':'continuous_unified','input_schema':self.registration['schema']}

    def complete(self,actor):return self.adapter.desk.actor_data[actor]['release'] is not None
    def all_complete(self):return all(self.complete(actor) for actor in self.actors)
    def business_state(self,actor):return self.adapter.desk.status(actor)
    def outcome(self,actor):return {'complete':self.complete(actor),'account':actor}
    def snapshot(self):
        return {'activated':self.activated,'actors':deepcopy(self.adapter.desk.actor_data),
                'action_count':len(self.adapter.calls)}

    def activity_signal(self,actor):
        # Shared work files can inform wake-ups, but no peer is named or signalled in the task.
        visible=self.world._visible_shared(actor)
        entries=[{'path':path,'sha256':row['sha256'],'event':'shared_file_changed'}
                 for path,row in visible.items() if row['author']!=actor]
        state=self.business_state(actor)
        digest=lambda value:sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
        return {'revision':digest([entries,state]),'case_revisions':{'delivery':digest(entries)},
                'case_entries':{'delivery':entries},'calendar_revision':digest(state),
                'calendar_components':{key:digest(value) for key,value in state.items()},
                'relevant_cross_job_records':len(entries)}

    def observed_calendar_revision(self, operation, result):
        if operation!='read_build_desk':return None
        return sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()

    def observed_calendar_components(self, operation, result):
        if operation!='read_build_desk':return {}
        return {key:sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
                for key,value in result.items()}

    def observed_activity_keys(self, operation, result):
        if operation!='bash':return set()
        from phase1.lab import shared_output_reads
        rows=shared_output_reads(self.world.shared.values(),None,result)
        observed={(row['path'],row['sha256']) for values in rows.values() for row in values}
        event=self.world.events[-1] if self.world.events else {}
        if event.get('operation')=='bash' and event.get('result')==result:
            observed.update((row['path'],row['sha256']) for row in event.get('notification_short_reads',[]))
        return observed

    def call(self,actor,step,name,arguments,*,elapsed_seconds=None):
        if not self.activated:raise ValueError('The registered input is not active')
        result=self.adapter.call(actor,name,arguments)
        event={'id':len(self.world.events)+1,'actor':actor,'step':step,'operation':name,
               'arguments':deepcopy(arguments),'result':deepcopy(result),'continuation':True,
               'shared_changes':[],'authored_artifacts':[],'adapter_event_id':len(self.adapter.calls),
               'start_group':self.world.plan[actor].get('start_group',0)}
        self.world.events.append(event)
        path=Path(self.world.operator)/'tool-commits'/f"{event['id']:06d}.json"
        if path.exists():raise RuntimeError('Refusing to replace tool evidence')
        atomic_json(path,{'event':deepcopy(event),'summary':self.world.summary(),
                          'continuation':self.snapshot()})
        return result

    def finalize(self):
        from phase2.build_record.record_monitor import monitor
        for actor in self.actors:
            self.adapter.desk.inspect_final(actor)
        observed=monitor(self.adapter.desk.root,self.actors,self.adapter.desk.events,accounts=self.registration['accounts'],receipt_defined=self.receipt_defined)
        result={'service_directory':'build-check-service','state':self.snapshot(),
                'mechanical_observation':observed}
        target=Path(self.world.operator)/'build-mechanical-observation.json'
        if target.exists():raise FileExistsError('Refusing to replace final observation')
        atomic_json(target,result)
        return result
