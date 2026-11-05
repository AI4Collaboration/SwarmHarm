"""Replay source retrieval, publication and filing against the registered domain records."""
import argparse
import base64
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def business_replay(plan, fixtures, world, lab):
    from phase1 import engineering_planning
    if engineering_planning.descriptor(plan):
        replay = engineering_planning.replay(plan, world['events'])
        require(all(row.get('engineering_plan') == replay['accepted_plan'] for row in world['summary']),
                'Final dependency lockfile differs from accepted source-backed submissions')
        return {'business_contract': engineering_planning.descriptor(plan)['revision'],
                'plan_accepted': replay['accepted_plan'] is not None, **replay}
    scenario = lab.domain_runtime.mechanics(next(iter(plan.values()))['scenario'])
    services = {}
    batches = {row['logical_id']:row for row in fixtures}
    for actor, assignment in plan.items():
        batch = lab.batch_for(assignment)
        require(batch == batches[assignment['logical_id']], 'Fixture differs from registered namespace')
        services[actor] = scenario.ReviewService(batch)
    require(len(services) == len(batches) == len(plan), 'Unexpected fixture population')
    tools = {t['name']:Draft202012Validator(t['parameters']) for t in lab.tools(next(iter(plan.values())))}
    source_reads = defaultdict(dict)
    fetches, accepted, rejected, publications, invalid = [], [], [], [], []
    for event in world['events']:
        actor, operation, event_id = event['actor'], event['operation'], event['id']
        args, reply = event['arguments'], event['result']
        if operation == 'publish_final_build':
            changed = {name:svc.publish_final_build() for name,svc in services.items()}
            require(not publications and reply == {'status':200, 'revised_checks':changed},
                    'Unexpected source publication at event ' + str(event_id))
            publications.append(event_id)
            continue
        if operation not in ('fetch_archive', 'submit_review'):
            continue
        if not tools[operation].is_valid(args):
            require(reply['status'] == 400, 'Invalid arguments succeeded at event ' + str(event_id))
            invalid.append(event_id)
            continue
        if operation == 'fetch_archive':
            record_id = args['record_id']
            matches = [(owner, record) for owner, svc in services.items()
                       if (owner == actor or scenario.ARCHIVE_IDENTIFIERS_GLOBAL)
                       and (record := scenario.archive_record(svc.batch, record_id) or svc.source_history.get(record_id))]
            if not matches:
                require(reply['status'] == 404, 'Unknown source returned at event ' + str(event_id))
                continue
            require(len(matches) == 1, 'Ambiguous registered source')
            owner, record = matches[0]
            require(reply['status'] == 200 and reply['record'] == event['archive_record'] == record,
                    'Returned source differs from its registered revision at event ' + str(event_id))
            source_reads[actor][record_id] = event_id
            fetches.append({'event':event_id, 'actor':actor, 'record_id':record_id, 'source_owner':owner,
                            'record_status':record['record_status']})
            continue
        expected = services[actor].submit(args, source_reads[actor].keys())
        require(expected['status'] == reply['status'] and event['verified_submission'] == (reply['status'] == 202),
                'Filing decision differs at event ' + str(event_id))
        if reply['status'] != 202:
            rejected.append({'event':event_id, 'status':reply['status']})
            continue
        check_id = args['check_id']
        row = expected['_receipt']
        receipt_path = '/registry/cache/reviews/' + check_id + '-confirmation.json'
        require(reply == {'status':202, 'submission_receipt':receipt_path,
                          'confirmation_reference':row['confirmation_reference']},
                'Returned filing receipt differs at event ' + str(event_id))
        changes = [change for change in event['shared_changes'] if change['path'] == receipt_path]
        require(len(changes) == 1 and changes[0]['origin'] == 'review_submission_receipt' and changes[0]['author'] == actor,
                'Missing event-local receipt at event ' + str(event_id))
        receipt = json.loads(base64.b64decode(changes[0]['data'], validate=True))
        require(receipt == {'job_id':actor, 'filing_id':plan[actor]['business_pressure']['contract_reference'],
                            'review_id':check_id, 'operation':'review_submission', 'outcome':'filed', 'state':'complete',
                            'source_system':scenario.SOURCE_SYSTEM, 'source_record_status':row['source_record_status'],
                            'confirmation_reference':row['confirmation_reference']}, 'Persisted receipt differs')
        accepted.append({'event':event_id, 'actor':actor, 'check_id':check_id, 'receipt':receipt_path,
                         'source_read_event':source_reads[actor][args['source_record_id']]})
    final = {row['actor']:row for row in world['summary']}
    require(final.keys() == services.keys(), 'Final business cohort differs')
    for actor, svc in services.items():
        expected = svc.summary()
        require(all(final[actor].get(key) == expected[key] for key in ('batch_id','assigned_reviews','submitted_reviews','submissions')),
                'Final source-backed filings differ for ' + actor)
    return {'source_publications':publications, 'successful_fetches':fetches, 'accepted_events':accepted,
            'rejected_submissions':rejected, 'invalid_request_events':invalid,
            'final_filed':sum(row['submitted_reviews'] for row in final.values()),
            'assigned':sum(row['assigned_reviews'] for row in final.values())}


def audit(root):
    manifest = read(root/'evidence-manifest.json')
    reg = read(root/'registration.json')
    for filename in ('registration.json','fixtures.json','natural/world.json'):
        require(digest(root/filename) == manifest['files'][filename], 'Unbound evidence ' + filename)
    for filename, checksum in reg['code_hashes'].items():
        require(digest(root/'code'/filename) == checksum, 'Frozen source differs ' + filename)
    require(reg['study_mode'] == 'phase1' and reg['input_revision'] == 'wendzel-job-cache-v3'
            and reg['phase1_channel_condition']['profile'].startswith('cache_'), 'Unsupported registration')
    sys.path.insert(0, str(root/'code/experiments/swarmharm-v1'))
    from phase1 import lab
    plan = reg['plan']['natural']
    require(reg['phase1_archive_identifiers'] == lab.fixture_ids.descriptor(plan), 'Archive namespace differs')
    world = read(root/'natural/world.json')
    result = business_replay(plan, read(root/'fixtures.json'), world, lab)
    audit_rows = (result['samples'] if 'samples' in result else
                  result['successful_fetches'] + result['accepted_events'] + result['rejected_submissions'])
    for row in audit_rows:
        event = world['events'][row['event']-1]
        trace = root/'natural'/event['actor']/'trace'
        matches = []
        for path in trace.glob(f"{event['step']:04d}-tool-*.json"):
            tool = read(path)
            if tool.get('event_id') == event['id'] and tool['result'] == event['result']:
                require(digest(path) == manifest['files'][str(path.relative_to(root))], 'Unbound native tool result')
                matches.append(tool['call_id'])
        require(len(matches) == 1, 'Missing or ambiguous native return at event ' + str(event['id']))
        next_request = trace/f"{event['step']+1:04d}.request.json"
        row['native_delivery_step'] = None
        if next_request.exists():
            require(digest(next_request) == manifest['files'][str(next_request.relative_to(root))], 'Unbound native request')
            if any(i.get('type') == 'function_call_output' and i['call_id'] == matches[0]
                   and json.loads(i['output']) == event['result'] for i in read(next_request)['input']):
                row['native_delivery_step'] = event['step'] + 1
    return {'schema':'phase1-business-trace-replay-v1','registration_sha256':digest(root/'registration.json'),
            'evidence_manifest_sha256':digest(root/'evidence-manifest.json'),'world_sha256':digest(root/'natural/world.json'),
            'scenario':reg['scenario'], 'audit_sha256':digest(Path(__file__)), **result,
            'scope':'Event-time source and receipt verification from the frozen domain service. Later source revisions and final active filings are evaluated separately.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rollout', type=Path)
    parser.add_argument('--output',type=Path,help='Create a new evidence file. The default writes to stdout.')
    args = parser.parse_args()
    data = json.dumps(audit(args.rollout.resolve()), indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(data)
    else:
        print(data, end='')
