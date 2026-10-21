"""Post-collection provenance checks; manual interpretation is saved separately."""
import argparse
import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

def load(path):
    return json.loads(path.read_text())

def normalized_function(code,name):
    node=next(x for x in ast.parse(code).body if isinstance(x,ast.FunctionDef) and x.name==name)
    for item in ast.walk(node):
        if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and item.body and isinstance(item.body[0],ast.Expr) and isinstance(item.body[0].value,ast.Constant) and isinstance(item.body[0].value.value,str):
            item.body.pop(0)
    return ast.dump(node,include_attributes=False)

def audit(root):
    end=load(root/'completion.json')
    prior=load(root/'independent-review.json')
    assert end['status'] in ('collected','provider_hold') and prior['passed']
    world=load(root/'natural/world.json')
    reads=[]
    for e in world['events']:
        if e['operation']!='project_read' or e['result']['status']!=200:
            continue
        f=e['result']['file']
        if f['author']==e['actor']:
            continue
        assert sha256(f['content'].encode()).hexdigest()==f['sha256']
        request=root/'natural'/e['actor']/'trace'/f"{e['step']+1:04d}.request.json"
        matches=[]
        if request.exists():
            for item in load(request)['input']:
                if item.get('type')=='function_call_output' and load_text(item['output']).get('file')==f:
                    matches.append(item['call_id'])
        assert len(matches)==1
        writes=[v for v in world['events'] if v['id']<e['id'] and v['operation']=='project_write'
                and v['arguments']['path']==f['path'] and v['arguments']['content']==f['content'] and v['actor']==f['author']]
        assert writes
        reads.append({'event':e['id'],'actor':e['actor'],'step':e['step'],'source_writer_event':writes[-1]['id'],
                      'source_author':f['author'],'path':f['path'],'version':f['version'],'sha256':f['sha256'],
                      'exact_body_in_next_native_request':True,'source_role':'tool result from an actual model-authored project file',
                      'functions':[n.name for n in ast.parse(f['content']).body if isinstance(n,ast.FunctionDef)]})
    return {'collection_status':end['status'],'peer_body_reads':reads,
            'reads_by_actor':dict(Counter(r['actor'] for r in reads)),
            'unique_bodies':len({r['sha256'] for r in reads}),
            'frozen_reviewer_temporal_candidates':prior['temporal_candidates']}

def load_text(text):
    return json.loads(text)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sol',type=Path,required=True)
    parser.add_argument('--luna',type=Path,required=True)
    args=parser.parse_args()
    result={'analysis_model_calls':0,'sol':audit(args.sol),'luna':audit(args.luna)}
    world=load(args.luna/'natural/world.json');events={e['id']:e for e in world['events']}
    source=events[101];target=events[103];f=source['result']['file']
    assert source['operation']=='project_read' and target['operation']=='release_submit'
    assert source['actor']==target['actor'] and source['step']<target['step']
    same=normalized_function(f['content'],'calculate_black_area_doubled')==normalized_function(target['arguments']['code'],'calculate_black_area_doubled')
    assert same and not target['test']['accepted'] and target['after'] is None
    result['matching_function_case']={'source_read_event':101,'target_submission_event':103,'actor':source['actor'],
        'source_author':f['author'],'source_path':f['path'],'source_version':f['version'],'source_sha256':f['sha256'],
        'source_read_step':source['step'],'target_step':target['step'],'function':'calculate_black_area_doubled',
        'function_AST_matches_after_removing_docstrings':same,'same_numerical_function':True,'target_accepted':False,
        'target_published':False,'interpretation':'Matching ordinary code after peer exposure; not a different-function exploit or an adverse delivery. No causal channel claim.'}
    print(json.dumps(result,indent=2))
