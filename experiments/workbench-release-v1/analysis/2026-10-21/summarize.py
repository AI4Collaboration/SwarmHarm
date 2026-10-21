"""Summarize all sealed conditions after their independent reviews; no inference."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
FAMILY=HERE.parents[1]
def load(path):return json.loads(path.read_text())
conditions=[];initial=[];files=[];sources=[]
for provider in ('luna','sol','sol56'):
    root=FAMILY/'results'/('2026-10-21-'+provider)
    reg=load(root/'registration.json');end=load(root/'completion.json');review=load(root/'independent-review.json')
    assert review['passed'] and review['all_rechecks_repeat']
    initial.append(sha256((root/'initial-input-audit.json').read_bytes()).hexdigest())
    files.append(sha256((root/'initial-file-audit.json').read_bytes()).hexdigest());sources.append(reg['code_hashes'])
    world=load(root/'natural/world.json');states=load(root/'natural/actors.json')
    operations=Counter(e['operation'] for e in world['events']);owners={c['id']:actor for actor,item in world['plan'].items() for c in item['components']}
    wrong=[];registry=[]
    for e in world['events']:
        if e['operation']=='bash':
            refs=re.findall(r'/registry/builds/([^/\s]+)',e['arguments']['command'])
            if refs:registry.append({'event':e['id'],'actor':e['actor'],'components':refs,'all_self':all(owners.get(c)==e['actor'] for c in refs)})
        delivery=e.get('delivery_event',{});caller=delivery.get('actual_caller')
        if not caller or caller['correct']:continue
        unique={json.dumps(v,sort_keys=True):v for v in caller['wrong_responses']}
        wrong.append({'event':e['id'],'actor':e['actor'],'component':e['arguments']['component_id'],'function':world['plan'][e['actor']]['components'][0]['entry_point'],
            'step':e['step'],'code_sha256':sha256(delivery['arguments']['code'].encode()).hexdigest(),'unique_wrong_registered_inputs':list(unique.values()),'caller_completed':caller['caller_completed']})
    conditions.append({'provider':provider,'model':reg['model'],'pressure':reg['pressure'],'status':end['status'],'elapsed_seconds':end['elapsed_seconds'],
        'normal_gate_passed':load(root/'gate.json')['passed'],'experimental_planned':len(world['plan']),'experimental_started':len(states),
        'experimental_statuses':dict(Counter(v['status'] for v in states.values())),'experimental_unstarted':len(world['plan'])-len(states),
        'native_classifications':review['classifications'],'operations':dict(operations),'wrong_components':sum(v['ever_incorrect_delivery'] for v in world['summary']),
        'outstanding_wrong_components':sum(v['outstanding_incorrect_delivery'] for v in world['summary']),'wrong_publication_events':wrong,
        'peer_body_output_matches':review['peer_body_output_matches'],'temporal_candidates':review['temporal_candidates'],
        'explicit_registry_references':registry,'independent_rechecks':len(review['published_rechecks']),'all_rechecks_repeat':review['all_rechecks_repeat']})
result={'analysis_model_calls':0,'source_registration_commit':'22ca0df8','matched_initial_native_inputs':len(set(initial))==1,
    'matched_initial_files':len(set(files))==1,'matched_frozen_sources':all(v==sources[0] for v in sources),
    'conditions':conditions,'limits':'Six selected source functions per condition, not a population rate. Shared reads, timing and automatic metadata are not semantic adoption. Supplementary range tests were selected post hoc and are separate from these registered outcomes.'}
assert result['matched_initial_native_inputs'] and result['matched_initial_files'] and result['matched_frozen_sources']
dest=HERE/'coverage.json';assert not dest.exists();dest.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({c['model']:{'status':c['status'],'experimental_statuses':c['experimental_statuses'],'wrong_components':c['wrong_components'],'peer_body_matches':c['peer_body_output_matches']} for c in conditions}))
