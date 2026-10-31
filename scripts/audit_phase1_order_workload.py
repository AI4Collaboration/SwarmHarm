"""Count actual private cache occupancy and order use in an independently replayed native workload."""
from hashlib import sha256
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def audit(root):
    reg = read(root/'registration.json')
    world = read(root/'natural/world.json')
    cache = world['working_cache']
    replay = read(root/'phase1-cache-counterfactual.json')
    assert digest(root/'natural/world.json') == read(root/'evidence-manifest.json')['files']['natural/world.json'] == replay['world_sha256']
    assert digest(root/'registration.json') == replay['registration_sha256']
    condition = reg['phase1_channel_condition']
    assert condition['profile'] == cache['profile'] == replay['factual_profile']
    assert condition['mechanism'] != 'count' or condition['isolation'] == 'repaired'
    capacity = cache['capacity']
    use = {a:{'peak_entries':0, 'final_entries':0, 'status_events':[], 'order_choices':[], 'reported_evictions':[]}
           for a in reg['plan']['natural']}
    for event in world['events']:
        if event['actor'] not in use:
            continue
        actor = use[event['actor']]
        eid, op, reply = event['id'], event['operation'], event['result']
        for write in event.get('cache_writes', []):
            assert eid in replay['checked_cache_events'] or eid in replay['archive_warmings']
            if write['feature'] == 'count':
                assert sum(write['before'].values()) == actor['final_entries']
                actor['final_entries'] = sum(write['after'].values())
                assert 0 <= actor['final_entries'] <= capacity
                actor['peak_entries'] = max(actor['peak_entries'], actor['final_entries'])
        if reply.get('status') != 200:
            continue
        if op == 'cache_status':
            assert len(reply['keys']) == sum(reply['counts'].values()) == actor['final_entries']
            actor['status_events'].append(eid)
        elif op == 'cache_order':
            changes = [w for w in event['cache_writes'] if w['feature'] == 'order']
            assert len(changes) <= 1
            actor['order_choices'].append({'event':eid, 'order':reply['eviction_order'],
                                           'changed_effective_order':any(w['before'] != w['after'] for w in changes)})
        elif op == 'cache_store' and reply['evicted']:
            actor['reported_evictions'].append({'event':eid,'keys':reply['evicted']})
    for a, row in use.items():
        assert row['final_entries'] == len(cache['entries'][a])
    return {'schema':'phase1-native-order-workload-v1','registration_sha256':replay['registration_sha256'],
            'world_sha256':replay['world_sha256'],'replay_sha256':digest(root/'phase1-cache-counterfactual.json'),
            'program_sha256':digest(Path(__file__)),'capacity':capacity,'jobs':use,
            'any_job_reached_capacity':any(v['peak_entries'] == capacity for v in use.values()),
            'scope':'Observed workload and actual returned order choices. These counts leave motives and alternate model choices unidentified.'}


if __name__ == '__main__':
    summary = audit(Path(sys.argv[1]).resolve())
    if len(sys.argv) > 2:
        with Path(sys.argv[2]).open('x') as output:
            json.dump(summary, output, indent=2); output.write('\n')
    else:
        print(json.dumps(summary))
