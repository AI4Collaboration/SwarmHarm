import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

from botocore.config import Config

from cloud import SESSION, save


def collect(directory, output=None, policy=None, metadata_directory=None):
    output = directory if output is None else output
    metadata_directory = directory if metadata_directory is None else metadata_directory
    policy = json.loads((directory / 'recording-policy.json').read_text()) if policy is None else policy
    storages = {item['node']['id']: item['node'] for item in policy['dataStorages']['edges']}
    default = storages[policy['defaultDataStorageID']]
    assert default['type'] == 's3' and default['status'] == 'active'
    settings = default['settings']['s3']
    client = SESSION.client('s3', region_name=settings['region'],
        endpoint_url=settings['endpoint'] or None,
        config=Config(max_pool_connections=12, connect_timeout=10, read_timeout=60,
                      retries={'total_max_attempts': 2, 'mode': 'standard'}))
    binding = json.loads((directory / 'binding.json').read_text())
    jobs = []
    coverage = []
    list_calls = 0
    for index, host in enumerate(binding['hosts']):
        key = json.loads((directory / f'private-key-{index}.json').read_text())
        metadata = json.loads((metadata_directory / f'gateway-{index}.json').read_text())
        goals = json.loads((directory / host['id'] / 'var/lib/peer-operator/native-goals.json').read_text())['goals']
        assert len(goals) == 1
        requests = metadata['requests']['edges']
        for item in requests:
            request = item['node']
            storage = storages[request['dataStorageID']]
            assert storage['id'] == default['id']
            request_id = request['id'].rsplit('/', 1)[1]
            project_id = request['projectID'].rsplit('/', 1)[1]
            prefix = f'{project_id}/requests/{request_id}/'
            objects = []
            for page in client.get_paginator('list_objects_v2').paginate(Bucket=settings['bucketName'], Prefix=prefix):
                list_calls += 1
                objects.extend(page.get('Contents', []))
            expected = {prefix + name + '.json' for name in ('request_body', 'response_body', 'response_chunks')}
            for execution in request['executions']['edges']:
                node = execution['node']
                assert node['dataStorageID'] == default['id']
                execution_id = node['id'].rsplit('/', 1)[1]
                if node['status'] == 'completed':
                    expected.update(prefix + f'executions/{execution_id}/' + name + '.json'
                                    for name in ('request_body', 'response_body', 'response_chunks'))
            found = {obj['Key'] for obj in objects}
            if request['status'] == 'completed':
                assert expected <= found, (request['id'], sorted(expected - found))
            association = {'repeat': binding['repeat'], 'instance_id': host['id'],
                'api_key_id': key['id'], 'request_id': request['id'], 'session_id': goals[0]['thread_id'],
                'request_status': request['status']}
            coverage.append({**association, 'expected_objects': sorted(expected),
                             'stored_objects': sorted(found), 'executions': request['executions']})
            jobs.extend((association, obj) for obj in objects)
    def retrieve(job):
        association, obj = job
        path = output / 'stored-payloads' / obj['Key']
        path.parent.mkdir(parents=True, exist_ok=True)
        with client.get_object(Bucket=settings['bucketName'], Key=obj['Key'])['Body'] as body:
            raw = body.read()
        path.write_bytes(raw)
        value = json.loads(raw)
        assert len(raw) == obj['Size']
        if association['request_status'] == 'completed':
            assert value, obj['Key']
        components = obj['Key'].split('/')
        execution_id = components[components.index('executions') + 1] if 'executions' in components else None
        return {**association, 'execution_id': execution_id, 'object_key': obj['Key'],
                'bucket': settings['bucketName'], 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'nonempty_json': bool(value)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        receipts = list(pool.map(retrieve, jobs))
    report = {'requests': len(coverage), 'objects': len(receipts),
              'bytes': sum(row['bytes'] for row in receipts), 'coverage': coverage, 'receipts': receipts,
              's3_operations': {'list_calls': list_calls, 'get_calls': len(receipts)}}
    save(output, 'recording-verification.json', report)
    print(json.dumps({name: report[name] for name in ('requests', 'objects', 'bytes')}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--policy-probe', type=Path)
    parser.add_argument('--metadata-directory', type=Path)
    args = parser.parse_args()
    policy = json.loads(args.policy_probe.read_text())['policy'] if args.policy_probe else None
    collect(args.directory, output=args.output, policy=policy, metadata_directory=args.metadata_directory)


if __name__ == '__main__':
    main()
