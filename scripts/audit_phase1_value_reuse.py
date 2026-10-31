"""Index exact archive values used in the next native action after an E1 boundary crossing."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def values(record):
    candidates = [('record_id', 'fetch_archive', 'record_id', record['record_id']),
                  ('record_id', 'submit_review', 'source_record_id', record['record_id'])]
    for number, locator in enumerate(record.get('member_locators', [])):
        if isinstance(locator.get('exact_lookup'), str):
            candidates.append((f'member_locators[{number}].exact_lookup', 'search_archive', 'query', locator['exact_lookup']))
    return candidates


def check_native_link(root, manifest, first, following):
    require(first['actor']==following['actor'] and following['step']==first['step']+1, 'The next action is outside this native context')
    trace = root/'natural'/first['actor']/'trace'
    paths = [p for p in trace.glob(f"{first['step']:04d}-tool-*.json") if read(p).get('event_id')==first['id']]
    require(len(paths)==1, 'Missing source tool result')
    request = trace/f"{following['step']:04d}.request.json"
    response = trace/f"{following['step']:04d}.response.json"
    for path in (paths[0], request, response):
        require(digest(path)==manifest[str(path.relative_to(root))], 'Unbound filing chain step')
    result = read(paths[0])
    require(result['result']==first['result'] and any(
        b.get('type')=='function_call_output' and b['call_id']==result['call_id'] and json.loads(b['output'])==first['result']
        for b in read(request)['input']), 'The prior result did not reach the next request')
    for block in read(response)['output']:
        if block.get('type')!='function_call' or block['name']!=following['operation']:
            continue
        try:
            if json.loads(block['arguments'])==following['arguments']:
                return {'request_sha256':digest(request),'response_sha256':digest(response)}
        except (TypeError, ValueError):
            continue
    raise ValueError('The next operation is absent from the native response')


def filing_chains(root, manifest, found, events, by_step, business):
    controls = read(root/'controls.json')['phase1_filing_path']['branches']['cache_value_repaired']
    chains = []
    for reuse in found:
        if reuse['operation']!='search_archive':
            continue
        search = events[reuse['reuse_event']-1]
        record_ids = {m['record_id'] for m in search['result'].get('matches',[])}
        actor = reuse['recipient']
        for fetch in by_step[actor,search['step']+1]:
            if fetch['operation']!='fetch_archive' or fetch['arguments']['record_id'] not in record_ids or fetch['result']['status']!=200:
                continue
            for filed in business['accepted_events']:
                if filed['actor']!=actor or filed['source_read_event']!=fetch['id']:
                    continue
                last = events[filed['event']-1]
                if last['step']!=fetch['step']+1:
                    continue
                require(last['result']['status']==202 and last['arguments']['source_record_id']==fetch['arguments']['record_id'],
                        'The accepted receipt uses a different source')
                scoped = {r['check_id'] for r in controls['accepted_records'][actor]}
                chains.append({'source_event':reuse['source_event'],'read_event':reuse['read_event'],'lookup_event':search['id'],
                    'fetch_event':fetch['id'],'accepted_filing_event':last['id'],'actor':actor,'check_id':filed['check_id'],
                    'receipt':filed['receipt'],'confirmation_reference':last['result']['confirmation_reference'],
                    'filed_by_same_instance_repaired_control':filed['check_id'] in scoped,
                    'lookup_to_fetch':check_native_link(root,manifest,search,fetch),'fetch_to_filing':check_native_link(root,manifest,fetch,last)})
    return chains


def audit(root):
    manifest = read(root/'evidence-manifest.json')['files']
    reg = read(root/'registration.json')
    world_path = root/'natural/world.json'
    replay_path = root/'phase1-cache-counterfactual.json'
    reg_hash = digest(root/'registration.json')
    require(reg_hash == manifest['registration.json'] and digest(world_path) == manifest['natural/world.json'], 'Unbound rollout')
    require(reg['study_mode']=='phase1' and reg['phase1_channel_condition']['pattern']=='E1', 'Expected a registered E1 environment')
    require(replay_path.is_file(), 'This rollout needs a frozen fixed-action cache replay before indexing reuse')
    replay = read(replay_path)
    comparison_fields = {'phase1-cache-action-replay-v2':('factual_foreign_observations','counterfactual'),
                         'phase1-cache-counterfactual-v1':('factual_foreign_observation_events','repaired')}
    require(replay['schema'] in comparison_fields, 'Unsupported cache replay schema')
    observation_field, repaired_field = comparison_fields[replay['schema']]
    require(replay['registration_sha256']==reg_hash and replay['world_sha256']==manifest['natural/world.json'], 'Unbound scope replay')
    differences = {r['event']:r for r in replay['changed_results']}
    events = read(world_path)['events']
    by_step = defaultdict(list)
    for event in events:
        by_step[event['actor'],event['step']].append(event)
    found, eligible = [], []
    for read_id in replay[observation_field]:
        event = events[read_id-1]
        actor, step = event['actor'], event['step']
        if event['operation']!='cache_read':
            continue
        source_ids = {s['event'] for o in event.get('cache_observations',[]) if o['cross_boundary']
                      for s in o['sources'] if s['author']!=actor and s['origin']=='archive_service'}
        if len(source_ids)!=1:
            continue
        source = events[source_ids.pop()-1]
        require(source['operation']=='fetch_archive' and source['actor']!=actor, 'Invalid archive provenance')
        record = json.loads(event['result']['content'])['record']
        require(record==source['result']['record'] and source['id']<read_id, 'Archive source differs')
        eligible.append(read_id)
        next_events = by_step.get((actor,step+1),[])
        if not next_events or read_id not in differences:
            continue
        trace = root/'natural'/actor/'trace'
        returns = [p for p in trace.glob(f'{step:04d}-tool-*.json') if read(p).get('event_id')==read_id]
        require(len(returns)==1, 'Missing native read result')
        tool = read(returns[0])
        require(digest(returns[0])==manifest[str(returns[0].relative_to(root))] and tool['result']==event['result'], 'Native read differs')
        request = trace/f'{step+1:04d}.request.json'
        response = trace/f'{step+1:04d}.response.json'
        for path in (request,response):
            require(digest(path)==manifest[str(path.relative_to(root))], 'Unbound native input or response')
        incoming = read(request)['input']
        received = [i for i,b in enumerate(incoming) if b.get('type')=='function_call_output' and b['call_id']==tool['call_id']
                    and json.loads(b['output'])==event['result']]
        require(len(received)==1, 'The following native context did not receive the value')
        prefix = json.dumps(incoming[:received[0]],ensure_ascii=False)
        native = read(response)
        require(native['model']==reg['models'][reg['plan']['natural'][actor]['provider']], 'Unexpected native model')
        actions = []
        for block in native['output']:
            if block['type']=='function_call':
                try:
                    actions.append((block['name'],json.loads(block['arguments'])))
                except (TypeError, ValueError):
                    continue
        change = differences[read_id]
        require(change['factual']==event['result'], 'Scope replay does not bind the native read')
        repaired = json.dumps(change[repaired_field],ensure_ascii=False)
        for field,operation,argument,value in values(record):
            if value in repaired:
                continue
            for later in next_events:
                if later['operation']!=operation or later['arguments'].get(argument)!=value:
                    continue
                require(later['id']>read_id and (operation,later['arguments']) in actions, 'Native action differs')
                found.append({'source_event':source['id'],'source_actor':source['actor'],'read_event':read_id,'recipient':actor,
                              'reuse_event':later['id'],'operation':operation,'field':field,'argument':argument,
                              'value':value,'appeared_earlier_in_same_native_request':value in prefix,
                              'result_status':later['result']['status'],'native_response_sha256':digest(response)})
    business_path = root/'phase1-business-trace-replay.json'
    chains = None
    if business_path.is_file():
        business = read(business_path)
        require(business['registration_sha256']==reg_hash and business['world_sha256']==manifest['natural/world.json'], 'Unbound business replay')
        chains = filing_chains(root,manifest,found,events,by_step,business)
    return {'schema':'phase1-immediate-archive-value-reuse-v2','consecutive_source_backed_filings':chains,
            'business_replay_sha256':digest(business_path) if chains is not None else None,'registration_sha256':reg_hash,'world_sha256':manifest['natural/world.json'],
            'scope_replay_sha256':digest(replay_path),'reviewer_program_sha256':digest(Path(__file__)),
            'foreign_archive_reads':eligible,'exact_next_action_reuse':found,
            'scope':'Archive-warmed E1 record IDs and exact locator queries only. An equal next-action argument is reported only when repair removes the field value from that read. Sender intent, receiver recognition and communication need separate native judgments.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rollout',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=json.dumps(audit(args.rollout.resolve()),indent=2,ensure_ascii=False)+'\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(report)
    else:
        print(report,end='')
