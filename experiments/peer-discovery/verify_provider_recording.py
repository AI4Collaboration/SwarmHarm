import argparse
import gzip
import hashlib
import json
from pathlib import Path

from cloud import SESSION, save
from recording import policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', required=True, type=Path)
    args = parser.parse_args()
    settings = policy(args.meta_key)
    save(args.directory, 'recording-policy.json', settings)
    storage = next(edge['node'] for edge in settings['dataStorages']['edges']
                   if edge['node']['id'] == settings['defaultDataStorageID'])['settings']['s3']
    project = next(edge['node'] for edge in settings['projects']['edges']
                   if edge['node']['name'] == 'SWH-77-peer-discovery')['id'].rsplit('/', 1)[1]
    client = SESSION.client('s3', region_name=storage['region'])
    metadata = json.loads((args.directory / 'gateway.json').read_text())['requests']['edges']
    receipts = []
    expected_total = 0
    for edge in metadata:
        request = edge['node']
        prefix = f'{project}/requests/{request["id"].rsplit("/", 1)[1]}/'
        expected = {prefix + 'request_body.json'}
        if request['status'] == 'completed':
            expected.update(prefix + field + '.json' for field in ('response_body', 'response_chunks'))
        for execution in request['executions']['edges']:
            node = execution['node']
            base = prefix + f'executions/{node["id"].rsplit("/", 1)[1]}/'
            expected.add(base + 'request_body.json')
            if node['status'] == 'completed':
                expected.update(base + field + '.json' for field in ('response_body', 'response_chunks'))
        objects = [item for page in client.get_paginator('list_objects_v2').paginate(
            Bucket=storage['bucketName'], Prefix=prefix) for item in page.get('Contents', [])]
        assert expected <= {item['Key'] for item in objects}, request['id']
        expected_total += len(expected)
        for item in objects:
            with client.get_object(Bucket=storage['bucketName'], Key=item['Key'])['Body'] as body:
                raw = body.read()
            assert len(raw) == item['Size'] and json.loads(raw), item['Key']
            path = args.directory / 'stored-payloads' / (item['Key'] + '.gz')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(raw, mtime=0))
            receipts.append({'request_id': request['id'], 'object_key': item['Key'],
                             'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    result = {'requests': len(metadata), 'expected_objects': expected_total,
              'stored_objects': len(receipts), 'coverage_complete': True, 'receipts': receipts}
    save(args.directory, 'recording-verification.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'receipts'}))


if __name__ == '__main__':
    main()
