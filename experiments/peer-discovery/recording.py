import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

from botocore.config import Config

from cloud import SESSION, save
from repeat import gateway


def policy(meta_key):
    result = gateway(meta_key, 'recording-policy', '')
    assert all(result['storagePolicy'].values())
    storage = next(edge['node'] for edge in result['dataStorages']['edges']
                   if edge['node']['id'] == result['defaultDataStorageID'])
    assert storage['type'] == 's3' and storage['status'] == 'active', storage
    return result


def export(directory, meta_key):
    settings = policy(meta_key)
    save(directory, 'recording-policy-collection.json', settings)
    storage = next(edge['node'] for edge in settings['dataStorages']['edges']
                   if edge['node']['id'] == settings['defaultDataStorageID'])['settings']['s3']
    project = next(edge['node'] for edge in settings['projects']['edges']
                   if edge['node']['name'] == 'SWH-77-peer-discovery')
    project_id = project['id'].rsplit('/', 1)[1]
    client = SESSION.client('s3', region_name=storage['region'],
                            config=Config(max_pool_connections=16, connect_timeout=10, read_timeout=60))
    bucket = storage['bucketName']
    binding = json.loads((directory / 'binding.json').read_text())
    jobs = []
    metadata = []
    for index, host in enumerate(binding['hosts']):
        key = json.loads((directory / f'private-key-{index}.json').read_text())
        requests = gateway(meta_key, 'recording-export', key['id'])
        save(directory, f'gateway-{index}.json', requests)
        for edge in requests['requests']['edges']:
            request = edge['node']
            prefix = f'{project_id}/requests/{request["id"].rsplit("/", 1)[1]}/'
            objects = [item for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix)
                       for item in page.get('Contents', [])]
            names = {item['Key'] for item in objects}
            expected = {prefix + 'request_body.json'}
            if request['status'] == 'completed':
                expected.update(prefix + name + '.json' for name in ('response_body', 'response_chunks'))
            for execution in request['executions']['edges']:
                node = execution['node']
                base = prefix + f'executions/{node["id"].rsplit("/", 1)[1]}/'
                expected.add(base + 'request_body.json')
                if node['status'] == 'completed':
                    expected.update(base + name + '.json' for name in ('response_body', 'response_chunks'))
            assert expected <= names, {'request': request['id'], 'expected': sorted(expected), 'stored': sorted(names)}
            link = {'instance_id': host['id'], 'api_key_id': key['id'], 'request_id': request['id'],
                    'execution_ids': [item['node']['id'] for item in request['executions']['edges']],
                    'status': request['status'], 'objects': sorted(names)}
            metadata.append(link)
            jobs.extend((link, item) for item in objects)
    def retrieve(job):
        link, item = job
        path = directory / 'stored-payloads' / item['Key']
        path.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, item['Key'], str(path))
        raw = path.read_bytes()
        assert len(raw) == item['Size'] and json.loads(raw), item['Key']
        return {**link, 'object_key': item['Key'], 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        receipts = list(pool.map(retrieve, jobs))
    result = {'requests': len(metadata), 'objects': len(receipts), 'bytes': sum(row['bytes'] for row in receipts),
              'bucket': bucket, 'metadata': metadata, 'receipts': receipts,
              's3_get_requests': len(receipts), 's3_list_requests_lower_bound': len(metadata)}
    save(directory, 'recording-receipts.json', result)
    print(json.dumps({name: result[name] for name in ('requests', 'objects', 'bytes')}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    args = parser.parse_args()
    export(args.directory, args.meta_key)


if __name__ == '__main__':
    main()
