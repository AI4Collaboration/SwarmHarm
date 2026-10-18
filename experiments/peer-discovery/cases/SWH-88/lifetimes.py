import datetime
import hashlib
import json
from pathlib import Path
import sys

from remote import BASE

sys.path.insert(0, str(BASE / 'operator-code/experiments/peer-discovery'))
from cloud import EC2, SESSION, save


def main():
    hosts = {}
    for directory in BASE.glob('repeat-*'):
        if directory.is_dir():
            for path in (directory / 'contention').glob('*.json'):
                snapshot = json.loads(path.read_text())
                for host in snapshot['fleet']:
                    item = hosts.setdefault(host['instance_id'], dict(host, first_seen=snapshot['time_ns'] / 1e9))
                    item['first_seen'] = min(item['first_seen'], snapshot['time_ns'] / 1e9)
    starts = [json.loads(path.read_text())['created_at'] for path in BASE.glob('repeat-*/cloud.json')]
    start = datetime.datetime.fromtimestamp(min(starts) - 86400, datetime.timezone.utc)
    end = datetime.datetime.now(datetime.timezone.utc)
    client = SESSION.client('cloudtrail')
    previous_path = BASE / 'instance-lifetimes.json'
    previous = json.loads(previous_path.read_text())['instances'] if previous_path.exists() else {}
    records = {instance_id: previous.get(instance_id, {}) for instance_id in hosts}
    for page in EC2.get_paginator('describe_instances').paginate():
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:
                if instance['InstanceId'] in records:
                    records[instance['InstanceId']]['ec2_launch'] = {
                        'timestamp': instance['LaunchTime'].timestamp(), 'state': instance['State']['Name'],
                        'retrieved_at': end.isoformat()}
    omitted_launches = {}
    pages = 0
    event_counts = {}
    for name in ('RunInstances', 'TerminateInstances'):
        for page in client.get_paginator('lookup_events').paginate(
            LookupAttributes=[{'AttributeKey': 'EventName', 'AttributeValue': name}],
            StartTime=start, EndTime=end):
            pages += 1
            for event in page['Events']:
                body = json.loads(event['CloudTrailEvent'])
                signature = json.dumps({'event': name, 'response_keys': sorted((body.get('responseElements') or {}).keys()),
                                        'error_code': body.get('errorCode')}, sort_keys=True)
                event_counts[signature] = event_counts.get(signature, 0) + 1
                response = body.get('responseElements') or {}
                receipt = {'timestamp': event['EventTime'].timestamp(), 'event_id': event['EventId'],
                           'event_sha256': hashlib.sha256(event['CloudTrailEvent'].encode()).hexdigest()}
                if name == 'RunInstances' and response.get('omitted'):
                    specifications = body['requestParameters']['tagSpecificationSet']['items']
                    tags = {tag['key']: tag['value'] for item in specifications
                            if item['resourceType'] == 'instance' for tag in item['tags']}
                    if tags.get('parent') == 'SWH-77':
                        omitted_launches.setdefault((tags['issue'], tags['purpose']), []).append(receipt)
                for instance in response.get('instancesSet', {}).get('items', []):
                    instance_id = instance['instanceId']
                    if instance_id in records:
                        records[instance_id]['launch' if name == 'RunInstances' else 'termination'] = dict(
                            receipt, binding='instance_id_in_response')
    for instance_id, record in records.items():
        if 'launch' not in record:
            host = hosts[instance_id]
            candidates = [event for event in omitted_launches.get((host['issue'], host['purpose']), [])
                          if event['timestamp'] <= host['first_seen']]
            if 'ec2_launch' in record:
                candidates = [event for event in candidates
                              if abs(event['timestamp'] - record['ec2_launch']['timestamp']) <= 10]
            assert len(candidates) == 1, {'instance_id': instance_id, 'host': host,
                'ec2_launch': record.get('ec2_launch'), 'candidates': candidates,
                'events': omitted_launches.get((host['issue'], host['purpose']), [])}
            record['launch'] = dict(candidates[0], binding='issue_purpose_and_ec2_launch_join_to_snapshot',
                                    issue=host['issue'], purpose=host['purpose'], first_seen=host['first_seen'])
            if 'ec2_launch' in record:
                record['launch']['cloudtrail_timestamp'] = record['launch']['timestamp']
                record['launch']['timestamp'] = record['ec2_launch']['timestamp']
    report = {'retrieved_at': end.isoformat(), 'query_start': start.isoformat(),
              'pages': pages, 'instances': records, 'event_counts': event_counts}
    save(BASE, 'instance-lifetimes.json', report)
    assert all('launch' in record for record in records.values()), event_counts
    for directory in BASE.glob('repeat-*'):
        if directory.is_dir() and (directory / 'binding.json').exists():
            save(directory, 'instance-lifetimes.json', report)
    print(json.dumps({'instances': len(records), 'pages': pages,
                      'launches': sum('launch' in record for record in records.values()),
                      'terminations': sum('termination' in record for record in records.values())}))


if __name__ == '__main__':
    main()
