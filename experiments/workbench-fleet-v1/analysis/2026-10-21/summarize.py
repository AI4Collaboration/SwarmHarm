"""Read independently verified project evidence; no model calls or trajectory edits."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import json,re,statistics

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]/'results/2026-10-21-mixed'
def load(p):return json.loads(p.read_text())
reg=load(ROOT/'registration.json');end=load(ROOT/'completion.json');review=load(ROOT/'independent-review.json')
assert review['passed'] and review['all_rechecks_repeat']
world=load(ROOT/'natural/world.json');states=load(ROOT/'natural/actors.json');owners={c['id']:a for a,item in world['plan'].items() for c in item['components']}
by_provider={};publications=[];shared_commands=[]
for provider,model in reg['models'].items():
    assigned={a:v for a,v in world['plan'].items() if v['provider']==provider};started=[states[a] for a in assigned if a in states]
    components=[s for s in world['summary'] if s['owner'] in assigned]
    by_provider[provider]={'model':model,'planned':len(assigned),'started':len(started),'statuses':dict(Counter(v['status'] for v in started)),
        'unstarted':len(assigned)-len(started),'ever_wrong_components':sum(v['ever_incorrect_delivery'] for v in components),
        'currently_wrong_components':sum(v['outstanding_incorrect_delivery'] for v in components),'currently_published_components':sum(v['published'] for v in components),
        'steps':{'min':min(v['steps'] for v in started),'median':statistics.median(v['steps'] for v in started),'max':max(v['steps'] for v in started)},
        'interleaved_context_wall_seconds':{'min':min(v['elapsed_seconds'] for v in started),'median':statistics.median(v['elapsed_seconds'] for v in started),'max':max(v['elapsed_seconds'] for v in started)}}
for e in world['events']:
    d=e.get('delivery_event',{});caller=d.get('actual_caller')
    if caller:
        unique={json.dumps(v,sort_keys=True):v for v in caller['wrong_responses']}
        publications.append({'event':e['id'],'actor':e['actor'],'provider':world['plan'][e['actor']]['provider'],'component':e['arguments']['component_id'],
            'function':world['plan'][e['actor']]['components'][0]['entry_point'],'correct':caller['correct'],'caller_completed':caller['caller_completed'],
            'unique_wrong_inputs':list(unique.values())})
    if e['operation']=='bash':
        cmd=e['arguments']['command']
        if re.search(r'/registry|build-cache|job-history|find[^\n]*-L|rglob',cmd):
            refs=re.findall(r'(?:/registry/builds|/workspace/build-cache)/([^/\s]+)',cmd)
            shared_commands.append({'event':e['id'],'actor':e['actor'],'command':cmd,'explicit_components':refs,'all_explicit_components_own':all(owners.get(c)==e['actor'] for c in refs),
                'full_body_matches':len(e['full_body_output_matches']),'stdout':e['result'].get('stdout',''),'stderr':e['result'].get('stderr','')})
first=min(datetime.fromisoformat(v['started_at']) for v in states.values());finished=datetime.fromisoformat(end['finished_at'])
result={'analysis_model_calls':0,'collection_status':end['status'],'registration_commit':'b804b764','overall_elapsed_seconds':end['elapsed_seconds'],
    'experimental_project_wall_seconds':(finished-first).total_seconds(),'source_functions':6,'distinct_task_test_variants':len({(v['components'][0]['task_id'],v['components'][0]['variant_row']['test']) for v in world['plan'].values()}),
    'conditions':by_provider,'response_classifications':review['classifications'],'operations':dict(Counter(e['operation'] for e in world['events'])),
    'accepted_experimental_versions':len(publications),'incorrect_publication_events':sum(not v['correct'] for v in publications),'publications':publications,
    'peer_body_output_matches':review['peer_body_output_matches'],'temporal_candidates':review['temporal_candidates'],'source_rechecks':len(review['published_rechecks']),
    'all_rechecks_repeat':review['all_rechecks_repeat'],'shared_files':len(world['shared_files']),
    'limits':'One mixed project, six source functions, 64 different test variants. Assignment balances model/function counts but cases/history differ; descriptive counts are not model causal effects or population rates. Context wall time includes serial inference waiting. Automatic completion archival is not voluntary advice. Timing/body matches alone cannot prove adoption.'}
for name,value in (('coverage.json',result),('shared-command-review.json',shared_commands)):
    path=HERE/name;assert not path.exists();path.write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({'models':by_provider,'accepted_experimental_versions':len(publications),'peer_body_matches':result['peer_body_output_matches'],'shared_commands':len(shared_commands)}))
