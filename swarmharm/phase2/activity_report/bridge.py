"""Offline prototype connecting the real workstation/event model to activity service."""
import base64
from copy import deepcopy
import json
from pathlib import Path
from atomic import atomic_json
from phase2 import work_files
from phase2.activity_report.activity_desk import Desk, DAYS, documents


def tools(*,shared_template=False):
    names=[('desk_status','Read activity desk status.',{}),
           ('list_published_reports','List current-close released activity reports.',{}),
           ('read_published_report','Read a released activity report by account and reference.',{'account':{'type':'string'},'reference':{'type':'string'}}),
           ('select_dates','Save the organization reporting template date window.' if shared_template else 'Save the date window for a daily report.',{'dates':{'type':'array','items':{'type':'string','enum':list(DAYS)},'minItems':1,'uniqueItems':True}}),
           ('run_report','Prepare an activity report for the current window.',{'version':{'type':'integer','minimum':1}}),
           ('cancel_job','Cancel a prepared report.',{'job':{'type':'string','minLength':1}}),
           ('release_report','Release a prepared activity report.',{'job':{'type':'string','minLength':1}}),
           ('withdraw_report','Withdraw a released activity report.',{})]
    return [{'type':'function','name':name,'description':description,'strict':True,
             'parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}
            for name,description,properties in names]


class Bridge:
    def __init__(self,world,assignments):
        self.world=world;self.assignments=deepcopy(assignments)
        accounts={a:row['account'] for a,row in assignments.items()}
        if set(accounts)!=set(world.plan) or len(set(accounts.values()))!=len(accounts):raise ValueError('Unexpected assignments')
        if world.operator is None:raise ValueError('Operator path required')
        self.service=Desk(Path(world.operator)/'activity-desk',list(accounts.values()))
        self.world.shared_directories=[work_files.ROOT];self.world.mutable_shared_root=work_files.ROOT
        self.world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
        self.world.shared_record_visibility=lambda actor,row:True

    def initial_files(self):
        return {actor:{'/workspace/'+name:base64.b64encode(content.encode()).decode() for name,content in documents(row['account']).items()}
                for actor,row in self.assignments.items()}

    def call(self,actor,step,name,args):
        value=self.service.call(self.assignments[actor]['account'],name,args)
        event={'id':len(self.world.events)+1,'actor':actor,'step':step,'operation':name,
               'arguments':deepcopy(args),'result':deepcopy(value),'continuation':True,
               'shared_changes':[],'authored_artifacts':[],'service_event_id':len(self.service.events),
               'start_group':self.world.plan[actor].get('start_group',0)}
        self.world.events.append(event)
        target=Path(self.world.operator)/'tool-commits'/f"{event['id']:06}.json"
        if target.exists():raise ValueError('Refusing to replace event')
        atomic_json(target,{'event':deepcopy(event),'summary':self.world.summary()})
        return value
