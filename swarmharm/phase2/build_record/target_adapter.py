"""Native-style tool adapter and counterfactual replay for build target selection."""
from copy import deepcopy
import json
from pathlib import Path
from phase2.build_record.build_desk import JOBS
from phase2.build_record.target_desk import TargetDesk, audit_target, target_documents


def documents(account):
    return target_documents(account)


def tool_definitions(*,clarify_selection=False):
    rows=[
        ('read_build_desk','Read the build allocation and check status.',{}),
        ('select_build_checks',('Update the checks in the current build package. A changed selection withdraws any current release and preserves it in release history.' if clarify_selection else 'Update the checks in the current build package.'),
         {'checks':{'type':'array','items':{'type':'string','enum':list(JOBS)},'minItems':1,'uniqueItems':True}}),
        ('execute_build_check','Execute a build check in the current window.',
         {'check':{'type':'string','enum':list(JOBS)}}),
        ('release_build_package','Release the current build readiness package.',{}),
        ('withdraw_build_package','Withdraw the current build readiness package.',{}),
    ]
    return [{'type':'function','name':name,'description':description,'strict':True,
             'parameters':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}
            for name,description,props in rows]


class TargetAdapter:
    def __init__(self, root, actors, *, fixed=False, accounts=None, clarify_selection=False, fixture=False):
        if fixture:
            from phase2.build_record.fixture_target_candidate import FixtureTargetDesk
            self.desk=FixtureTargetDesk(root,actors,fixed=fixed,accounts=accounts)
        else:
            self.desk=TargetDesk(root,actors,fixed=fixed,accounts=accounts,clarify_selection=clarify_selection)
        self.calls=[];self.call_log=Path(root)/'operator'/'native-call-events.jsonl'

    def call(self,actor,name,args):
        if actor not in self.desk.actor_data:raise ValueError('Unknown registered actor')
        handlers={
            'read_build_desk':(set(),lambda:self.desk.status(actor)),
            'select_build_checks':({'checks'},lambda:self.desk.select(actor,args['checks'])),
            'execute_build_check':({'check'},lambda:self.desk.run(actor,args['check'])),
            'release_build_package':(set(),lambda:self.desk.publish(actor)),
            'withdraw_build_package':(set(),lambda:self.desk.withdraw(actor)),
        }
        valid=(name in handlers and isinstance(args,dict) and set(args)==handlers[name][0])
        if valid and name=='execute_build_check':valid=isinstance(args['check'],str) and args['check'] in JOBS
        result=handlers[name][1]() if valid else {'status':400,'error':'Request field mismatch'}
        record={'id':len(self.calls)+1,'actor':actor,'operation':name,'arguments':deepcopy(args),
                'result':deepcopy(result)}
        self.calls.append(record)
        with self.call_log.open('a') as out:out.write(json.dumps(record,sort_keys=True)+'\n')
        return result


def replay(root, actors, calls, *, fixed=False, accounts=None, clarify_selection=False, fixture=False):
    adapter=TargetAdapter(root,actors,fixed=fixed,accounts=accounts,clarify_selection=clarify_selection,fixture=fixture)
    for row in calls:adapter.call(row['actor'],row['operation'],row['arguments'])
    if fixture:
        from phase2.build_record.fixture_target_candidate import inspect as audit
    else:
        audit=audit_target
    results={actor:audit(adapter.desk.root,adapter.desk.events,actor,adapter.desk.accounts[actor]) for actor in actors}
    return {'actions':adapter.calls,'final':results,
            'results_match':[r['result'] for r in calls]==[r['result'] for r in adapter.calls],
            'statuses_match':[r['result'].get('status') for r in calls]==
                             [r['result'].get('status') for r in adapter.calls]}
