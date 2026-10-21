"""Check every required operational output, without changing admission gates."""
import argparse
import hashlib
import json
from pathlib import Path


def load(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def json_object(text):
    try:
        value=json.loads(text)
        return {'json_object':isinstance(value,dict),
                'error':None if isinstance(value,dict) else 'JSON is not an object'}
    except (TypeError,ValueError) as error:
        return {'json_object':False,'error':str(error)}


def analyze(root):
    independent=load(root/'independent-review.json')
    assert independent['passed'],'Require completed independent replay first'
    reg=load(root/'registration.json');finals=[];writes=[];coverage=[]
    for cell in [reg['calibration']]+reg['cells']:
        audit=load(root/cell['id']/'world.json')
        output_ids={e['object_id'] for e in audit['events']
                    if e.get('routine_task_output_path') and e['accepted']}
        owners={audit['state']['resources'][rid]['owner_actor'] for rid in output_ids}
        for actor in cell['plan']:
            coverage.append({'world':cell['id'],'actor':actor,'has_output':actor in owners})
        for rid in sorted(output_ids):
            resource=audit['state']['resources'][rid]
            finals.append({'world':cell['id'],'actor':resource['owner_actor'],
                'resource_id':rid,'version':resource['version'],**json_object(resource['content'])})
        for event in audit['events']:
            if event.get('routine_task_output_path') and event['accepted']:
                writes.append({'world':cell['id'],'actor':event['actor_id'],'event':event['event_id'],
                               **json_object(event['inputs']['content'])})
    source=Path(__file__).resolve();copy=root/'analysis-code'/('output-quality-'+sha(source)[:16]+'.py')
    copy.write_bytes(source.read_bytes())
    result={'model_calls':0,'independent_review_sha256':sha(root/'independent-review.json'),
        'analysis_code':{'path':str(copy.relative_to(root)),'sha256':sha(source)},
        'original_admission_gate_unchanged':True,
        'interpretation':'Postcollection JSON-format and output-presence quality checks. A failure remains a quality failure; it neither changes the registered model-admission gate nor erases a behavioral trajectory.',
        'coverage':coverage,'final_output_objects':finals,'all_accepted_output_writes':writes,
        'passed':all(x['has_output'] for x in coverage) and all(x['json_object'] for x in finals+writes)}
    (root/'output-quality.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output_quality_passed':result['passed'],'final_outputs':len(finals),
        'accepted_writes':len(writes),'missing_outputs':sum(not x['has_output'] for x in coverage),
        'non_json_objects':sum(not x['json_object'] for x in finals+writes)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    analyze(parser.parse_args().output.resolve())
