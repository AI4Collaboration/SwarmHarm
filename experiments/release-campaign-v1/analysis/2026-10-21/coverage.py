"""Post-collection coverage counts only; does not call models or alter a study."""
import argparse
from collections import Counter
import json
from pathlib import Path

def load(path):
    return json.loads(path.read_text())

def coverage(root):
    reg=load(root/'registration.json')
    end=load(root/'completion.json')
    actors=[]
    for actor,item in reg['plan']['natural'].items():
        p=root/'natural'/actor/'result.json'
        state=load(p) if p.exists() else None
        actors.append({'actor':actor,'wave':item['wave'],'started':state is not None,
                       'saved_state':state['status'] if state else 'unstarted',
                       'steps':state.get('steps',0) if state else 0,
                       'tools':state.get('tools',0) if state else 0,
                       'completed_context':bool(state and state['status']=='completed')})
    w=load(root/'natural/world.json') if (root/'natural/world.json').exists() else {'events':[],'summary':[],'components':{}}
    events=w['events']
    read={e['arguments']['component_id'] for e in events if e['operation']=='component_read' and e['result']['status']==200}
    submitted={e['arguments']['component_id'] for e in events if e['operation']=='release_submit' and isinstance(e.get('arguments'),dict) and e['arguments'].get('component_id') in w['components']}
    summaries={c['component_id']:c for c in w['summary']}
    rows=[]
    for a,item in reg['plan']['natural'].items():
        started=next(v for v in actors if v['actor']==a)['started']
        for c in item['components']:
            s=summaries.get(c['id'],{})
            rows.append({**c,'actor':a,'wave':item['wave'],'started':started,'read':c['id'] in read,
                         'submitted':c['id'] in submitted,
                         **{k:s.get(k,False) for k in ('published','ever_incorrect_delivery','outstanding_incorrect_delivery','recovered')}})
    by_condition=[]
    for task,split in sorted({(r['task_id'],r['split']) for r in rows}):
        group=[r for r in rows if (r['task_id'],r['split'])==(task,split)]
        by_condition.append({'task_id':task,'function':group[0]['entry_point'],'split':split,
                             'planned':len(group),
                             **{k:sum(bool(r[k]) for r in group) for k in ('started','read','submitted','published','ever_incorrect_delivery','outstanding_incorrect_delivery','recovered')}})
    classifications=load(root/'response-review.json')
    return {'provider':reg['provider'],'collection_status':end['status'],'elapsed_seconds':end['elapsed_seconds'],
            'contexts_started':sum(a['started'] for a in actors),'contexts_completed':sum(a['completed_context'] for a in actors),
            'contexts_unstarted':sum(not a['started'] for a in actors),'actors':actors,
            'components':rows,'by_function_and_variant':by_condition,
            'operations':dict(Counter(e['operation'] for e in events)),
            'provider_classifications':dict(Counter(c['status'] for c in classifications)),
            'errors':[c for c in classifications if c['status'] in ('provider_error','provider_filter','native_refusal','text_refusal_candidate')],
            'interpretation':'Coverage only. A completed context need not have published a component. Read, submission, publication and actual wrong delivery have separate denominators. Provider-halted saved running states are unfinished, not completed negative outcomes.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    print(json.dumps(coverage(args.root.resolve()),indent=2))
