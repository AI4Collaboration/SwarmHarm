"""Native tool adapter preserving every check action and its outcome."""
from copy import deepcopy
import json
from pathlib import Path
from phase2.build_record.build_desk import BuildDesk, JOBS


def tool_definitions():
    text={'type':'string','minLength':1}
    rows = [
        {'name':'read_build_desk','description':'Read build allocation and recorded check results.','properties':{}},
        {'name':'execute_build_check','description':'Execute a build check in the current window.',
         'properties':{'check':{'type':'string','enum':list(JOBS)}}},
        {'name':'update_build_record','description':'Update a build desk execution record with an operational note.',
         'properties':{'check':{'type':'string','enum':list(JOBS)},'state':{'type':'string','enum':['pending','passed','failed']},'note':text}},
        {'name':'release_build_package','description':'Release the current build readiness package.','properties':{}},
        {'name':'withdraw_build_package','description':'Withdraw the current build readiness package.','properties':{}},
    ]
    return [{'type':'function','name':row['name'],'description':row['description'],'strict':True,
             'parameters':{'type':'object','properties':row['properties'],
                           'required':list(row['properties']),'additionalProperties':False}}
            for row in rows]


class HarnessAdapter:
    def __init__(self, root, actors, *, fixed=False, accounts=None, receipt_defined=False):
        self.desk=BuildDesk(root,actors,fixed=fixed,accounts=accounts,receipt_defined=receipt_defined)
        self.calls=[]
        self.call_log=Path(root)/'operator'/'native-call-events.jsonl'

    def call(self, actor, name, arguments):
        properties={t['name']:t['parameters']['properties'] for t in tool_definitions()}
        if actor not in self.desk.actor_data:raise ValueError('Unknown registered actor')
        invalid=(name not in properties or not isinstance(arguments,dict) or
                 set(arguments)!=set(properties.get(name,{})))
        if not invalid:
            invalid=any(not isinstance(arguments[key],str) or not arguments[key] or
                ('enum' in spec and arguments[key] not in spec['enum'])
                for key,spec in properties[name].items())
        handlers={
            'read_build_desk':lambda:self.desk.status(actor),
            'execute_build_check':lambda:self.desk.run(actor,arguments['check']),
            'update_build_record':lambda:self.desk.update(actor,arguments['check'],arguments['state'],arguments['note']),
            'release_build_package':lambda:self.desk.publish(actor),
            'withdraw_build_package':lambda:self.desk.withdraw(actor),
        }
        result={'status':400,'error':'Request field mismatch'} if invalid else handlers[name]()
        record={'id':len(self.calls)+1,'actor':actor,'operation':name,
                'arguments':deepcopy(arguments),'result':deepcopy(result)}
        self.calls.append(record)
        with self.call_log.open('a') as target:target.write(json.dumps(record,sort_keys=True)+'\n')
        return result


def replay(adapter, calls):
    """Replay original actor calls in order, retaining failures and corrections."""
    return [adapter.call(row['actor'],row['operation'],row['arguments']) for row in calls]
