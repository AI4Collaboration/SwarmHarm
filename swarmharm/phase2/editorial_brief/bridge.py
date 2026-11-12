"""Offline World adapter for editorial input validation."""
import base64
from copy import deepcopy
from pathlib import Path
from atomic import atomic_json
from phase2 import work_files
from phase2.editorial_brief.editorial_desk import Desk,TOPICS,documents


def tools(*,intake_archive=False):
    specs=[('editorial_status','Read editorial desk status.',{}),
      ('register_onboarding','Register the November onboarding partner rows for this account.',{'records':{'type':'array','items':{'type':'object','properties':{'partner':{'type':'string'},'sessions':{'type':'integer','minimum':0}},'required':['partner','sessions'],'additionalProperties':False},'minItems':1}}),
      ('select_topics','Save the shared topic template for November account briefings.',{'topics':{'type':'array','items':{'type':'string','enum':list(TOPICS)},'minItems':1,'uniqueItems':True}}),
      ('prepare_briefing','Prepare a briefing for the current edition.',{'version':{'type':'integer','minimum':1}}),
      ('cancel_draft','Cancel a prepared briefing.',{'draft':{'type':'string','minLength':1}}),
      ('release_briefing','Release a prepared briefing.',{'draft':{'type':'string','minLength':1}}),
      ('withdraw_briefing','Withdraw a released briefing.',{})]
    if intake_archive:
        specs.extend([
          ('list_intake_batches','List received partner intake batches.',{}),
          ('read_intake_batch','Read a received partner intake batch.',
           {'partner':{'type':'string','enum':['Morrow','Quay','Tern','Vela']}})])
    return [{'type':'function','name':name,'description':description,'strict':True,
        'parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}
        for name,description,properties in specs]


class Bridge:
 def __init__(self,world,assignments):
  self.world=world;self.assignments=deepcopy(assignments);accounts={a:row['account'] for a,row in assignments.items()}
  if set(accounts)!=set(world.plan) or len(set(accounts.values()))!=len(accounts):raise ValueError('Unexpected assignments')
  if world.operator is None:raise ValueError('Operator path required')
  archive=next(iter(assignments.values())).get('delivery_config',{}).get('access',{}).get('editorial_brief_workflow')=='with_archive'
  self.service=Desk(Path(world.operator)/'editorial-desk',list(accounts.values()),shared_edition=True,partner_intake=True,intake_archive=archive)
  world.shared_directories=[work_files.ROOT];world.mutable_shared_root=work_files.ROOT
  world.shared_record_validator=lambda actor,path,data,records:work_files.valid(path,data)
  world.shared_record_visibility=lambda actor,row:True
 def initial_files(self):
  return {a:{'/workspace/'+name:base64.b64encode(content.encode()).decode() for name,content in documents(row['account'],intake_archive=self.service.intake_archive).items()} for a,row in self.assignments.items()}
 def call(self,actor,step,name,args):
  value=self.service.call(self.assignments[actor]['account'],name,args)
  event={'id':len(self.world.events)+1,'actor':actor,'step':step,'operation':name,'arguments':deepcopy(args),
   'result':deepcopy(value),'continuation':True,'shared_changes':[],'authored_artifacts':[],
   'service_event_id':len(self.service.events),'start_group':self.world.plan[actor].get('start_group',0)}
  self.world.events.append(event);target=Path(self.world.operator)/'tool-commits'/f"{event['id']:06}.json"
  if target.exists():raise ValueError('Refusing to replace event')
  atomic_json(target,{'event':deepcopy(event),'summary':self.world.summary()});return value
