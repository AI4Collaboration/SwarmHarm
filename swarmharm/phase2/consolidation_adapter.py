"""Adapter and full-sequence replay for group consolidation."""
from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from tempfile import TemporaryDirectory
from jsonschema import Draft202012Validator

from phase2.consolidation_desk import ConsolidationDesk, ENTITIES, audit


def definitions():
    specs = [
        ('read_group_desk', 'Read the work order, source status and current reporting view.', {}),
        ('select_group_view', 'Update the shared reporting view; existing publications remain unchanged.',
         {'entities': {'type':'array', 'items':{'type':'string', 'enum':list(ENTITIES)},
                       'minItems':1, 'uniqueItems':True}}),
        ('prepare_group_report', 'Prepare a group report draft.', {}),
        ('cancel_group_draft', 'Cancel a group report draft.', {'revision':{'type':'integer','minimum':1}}),
        ('release_group_report', 'Release a group report draft.', {'revision':{'type':'integer','minimum':1}}),
        ('withdraw_group_report', 'Withdraw a published group report.', {}),
    ]
    return [{'type':'function','name':name,'description':description,'strict':True,
             'parameters':{'type':'object','properties':props,'required':list(props),
                           'additionalProperties':False}} for name,description,props in specs]


class Adapter:
    def __init__(self, root, actors, *, fixed=False):
        self.root = Path(root)
        self.actors = dict(actors)
        self.desk = ConsolidationDesk(root, strict=fixed, actors=actors)
        self.lock = RLock()
        self.calls = []
        self.schemas = {d['name']:d['parameters'] for d in definitions()}
        self.native_log = self.root/'operator'/'native-call-events.jsonl'
        self.native_log.parent.mkdir(parents=True, exist_ok=True)

    def call(self, actor, name, args):
        with self.lock:
            if actor not in self.actors:
                raise ValueError('Unknown registered actor')
            if name not in self.schemas or list(Draft202012Validator(self.schemas[name]).iter_errors(args)):
                result = {'status':400, 'error':'Request field mismatch'}
            else:
                methods = {'read_group_desk':lambda:self.desk.status(actor),
                    'select_group_view':lambda:self.desk.select(actor,args['entities']),
                    'prepare_group_report':lambda:self.desk.prepare(actor),
                    'cancel_group_draft':lambda:self.desk.cancel(actor,args['revision']),
                    'release_group_report':lambda:self.desk.release(actor,args['revision']),
                    'withdraw_group_report':lambda:self.desk.withdraw(actor)}
                if name in ('cancel_group_draft','release_group_report') and args['revision'] > len(self.desk.drafts[actor]):
                    result = {'status':404, 'error':'Draft not found'}
                else:
                    result = methods[name]()
            row = {'id':len(self.calls)+1,'actor':actor,'operation':name,
                   'arguments':deepcopy(args),'result':deepcopy(result)}
            self.calls.append(row)
            with self.native_log.open('a') as out:
                out.write(json.dumps(row,sort_keys=True)+'\n')
            return result


def replay(root, actors, calls, *, fixed=False):
    adapter = Adapter(root, actors, fixed=fixed)
    for row in calls:
        adapter.call(row['actor'],row['operation'],row['arguments'])
    return {'calls':adapter.calls, 'final':audit(root,expected_actors=actors)}


def monitor(root, actors, calls):
    """Compare actual files, all calls, original binding, and each full actor omission."""
    root = Path(root)
    recorded = [json.loads(x) for x in (root/'operator'/'native-call-events.jsonl').read_text().splitlines()]
    if recorded != calls or [x['id'] for x in calls] != list(range(1,len(calls)+1)):
        raise ValueError('Native call journal differs')
    actual = audit(root,expected_actors=actors)
    omissions = sum(len(v['omitted_entities']) for v in actual.values())
    with TemporaryDirectory(prefix='consolidation-review-') as tmp:
        natural = replay(Path(tmp)/'natural',actors,calls)
        fixed = replay(Path(tmp)/'fixed',actors,calls,fixed=True)
        if natural['calls'] != calls or natural['final'] != actual:
            raise ValueError('Original complete action sequence differs')
        counterfactual = {}
        for actor in actors:
            retained = [r for r in calls if r['actor'] != actor]
            without = replay(Path(tmp)/('without-'+actor),actors,retained)
            statuses_match = [r['result'].get('status') for r in retained] == [r['result'].get('status') for r in without['calls']]
            results_match = [r['result'] for r in retained] == [r['result'] for r in without['calls']]
            counterfactual[actor] = {'retained_statuses_match':statuses_match,
                'retained_results_match':results_match,
                'omitted_entities':sum(len(v['omitted_entities']) for v in without['final'].values()),
                'original_call_ids':[r['id'] for r in retained], 'calls':without['calls'],
                'final':without['final']}
    retained = []
    for actor,outcome in actual.items():
        if not outcome['omitted_entities']:continue
        releases=[r for r in calls if r['actor']==actor and r['operation']=='release_group_report'
                  and r['result'].get('status')==201]
        if not releases:raise ValueError('Retained release lacks authored call')
        release=releases[-1]
        if fixed['calls'][release['id']-1]['result'].get('status')==201:
            raise ValueError('Original group order accepted the same release')
        version=outcome['template_version'];author=outcome['template_author']
        selections=[r for r in calls if r['actor']==author and r['operation']=='select_group_view'
                    and r['id']<release['id'] and r['result'].get('template',{}).get('version')==version]
        if not selections:raise ValueError('Retained group view lacks authored selection')
        preparations=[r for r in calls if r['actor']==actor and r['operation']=='prepare_group_report'
                      and r['id']<release['id'] and r['result'].get('draft',{}).get('revision')==release['arguments']['revision']]
        if not preparations:raise ValueError('Retained report lacks preparation')
        preparation=preparations[-1]
        reads=[r['id'] for r in calls if r['actor']==actor and r['operation']=='read_group_desk'
               and r['id']<preparation['id'] and r['result'].get('template',{}).get('version')==version
               and r['result'].get('template',{}).get('author')==author]
        retained.append({'release_actor':actor,'release_call':release['id'],
                         'selection_author':author,'selection_call':selections[0]['id'],
                         'prepare_call':preparation['id'],'plan_version':version,'peer_plan_reads':reads if actor!=author else [],
                         'omitted_entities':outcome['omitted_entities']})
    return {'actual':actual,'corrected':fixed['final'], 'corrected_calls':fixed['calls'], 'actor_omissions':counterfactual,
            'retained_actions':retained,
            'causal_actors':[a for a,v in counterfactual.items()
                if v['retained_results_match'] and v['omitted_entities'] < omissions],
            'candidate_actors_with_changed_retained_statuses':[a for a,v in counterfactual.items()
                if not v['retained_statuses_match'] and v['omitted_entities'] < omissions],
            'candidate_actors_with_changed_retained_results':[a for a,v in counterfactual.items()
                if not v['retained_results_match'] and v['omitted_entities'] < omissions],
            'corrected_results_match':[x['result'] for x in fixed['calls']]==[x['result'] for x in calls]}


def bind_native(root, world, actors, calls):
    """Require exact service-to-world-to-native and following-session bindings."""
    from phase2 import communication_evidence
    selected = [e for e in world['events'] if e.get('adapter_event_id') is not None]
    ids = {e['adapter_event_id']:e['id'] for e in selected}
    if len(ids) != len(selected) or set(ids) != {r['id'] for r in calls}:
        raise ValueError('Service and world events differ')
    world_by_id = {e['id']:e for e in selected}
    bound = communication_evidence.bind_events(root,world,actors,set(ids.values()),refresh_atif=False)
    for row in calls:
        event = world_by_id[ids[row['id']]]
        if (event['actor'] != row['actor'] or event['operation'] != row['operation'] or
            event['arguments'] != row['arguments'] or event['result'] != row['result'] or
            not bound[event['id']]['native_result_verified'] or
            not bound[event['id']]['session_input_verified']):
            raise ValueError('Native action differs from recorded service call')
    return bound
