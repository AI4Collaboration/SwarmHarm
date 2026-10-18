import argparse
import concurrent.futures
import gzip
import hashlib
import json
import time
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


def export(directory, meta_key, session_source='host-archive'):
    prior_path = directory / 'recording-receipts.json'
    prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
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
    cloud = json.loads((directory / 'cloud.json').read_text())
    jobs = []
    metadata = []
    coverage = []
    list_requests = 0
    for index, host in enumerate(binding['hosts']):
        if session_source == 'host-archive':
            goal = json.loads((directory / host['id'] / 'var/lib/peer-operator/native-goals.json').read_text())['goals'][0]
            session_id = goal['thread_id']
        else:
            assert session_source == 'launch-receipts'
            launch_path = directory / f'{host["id"]}-launch-verification.json'
            session_id = (json.loads(launch_path.read_text())['native-goals']['goals'][0]['thread_id']
                          if launch_path.exists() else None)
        key = json.loads((directory / f'private-key-{index}.json').read_text())
        requests = gateway(meta_key, 'recording-export', key['id'])
        save(directory, f'gateway-{index}.json', requests)
        for edge in requests['requests']['edges']:
            request = edge['node']
            prefix = f'{project_id}/requests/{request["id"].rsplit("/", 1)[1]}/'
            objects = []
            for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
                list_requests += 1
                objects.extend(page.get('Contents', []))
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
            coverage.append({'request_id': request['id'], 'expected_objects': sorted(expected),
                             'stored_expected_objects': sorted(expected & names),
                             'unrecorded_objects': sorted(expected - names)})
            link = {'issue': cloud['issue'], 'repeat': binding['repeat'], 'session_id': session_id,
                    'session_binding_source': session_source,
                    'instance_id': host['id'], 'api_key_id': key['id'], 'request_id': request['id'],
                    'execution_ids': [item['node']['id'] for item in request['executions']['edges']],
                    'status': request['status'], 'objects': sorted(names)}
            metadata.append(link)
            jobs.extend((link, item) for item in objects)
    def retrieve(job):
        link, item = job
        path = directory / 'stored-payloads' / (item['Key'] + '.gz')
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.exists()
        if existing:
            raw = gzip.decompress(path.read_bytes())
        else:
            with client.get_object(Bucket=bucket, Key=item['Key'])['Body'] as body:
                raw = body.read()
        assert len(raw) == item['Size'] and json.loads(raw), item['Key']
        path.write_bytes(gzip.compress(raw, mtime=0))
        return {**link, 'object_key': item['Key'], 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'local_compression': 'gzip',
                'compressed_bytes': path.stat().st_size, 'retrieved_in_this_export': not existing,
                's3_last_modified': item['LastModified'].isoformat(),
                'storage_gib_hours_until_export': len(raw) / 2**30 * max(0, time.time() - item['LastModified'].timestamp()) / 3600}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        receipts = list(pool.map(retrieve, jobs))
    total_gets = prior.get('s3_get_requests', 0) + sum(row['retrieved_in_this_export'] for row in receipts)
    total_lists = prior.get('s3_list_requests', prior.get('s3_list_requests_lower_bound', 0)) + list_requests
    result = {'requests': len(metadata), 'objects': len(receipts), 'bytes': sum(row['bytes'] for row in receipts),
              'bucket': bucket, 'metadata': metadata, 'receipts': receipts,
              'coverage': coverage,
              'coverage_complete': all(not row['unrecorded_objects'] for row in coverage),
              'expected_objects': sum(len(row['expected_objects']) for row in coverage),
              'stored_expected_objects': sum(len(row['stored_expected_objects']) for row in coverage),
              's3_get_requests': total_gets, 's3_list_requests': total_lists,
              's3_standard_cost_estimate_usd': {
                  'retrieval': total_gets * 0.00000043,
                  'listing': total_lists * 0.0000054,
                  'object_write_lower_bound': len(receipts) * 0.0000054,
                  'storage_until_export': sum(row['storage_gib_hours_until_export'] for row in receipts) / 730 * 0.0245,
                  'monthly_storage_at_exported_bytes': sum(row['bytes'] for row in receipts) / 2**30 * 0.0245},
              'cost_basis': 'Frankfurt Standard prices; observed exported objects; request receipts retain collection counts'}
    save(directory, 'recording-receipts.json', result)
    print(json.dumps({name: result[name] for name in ('requests', 'objects', 'bytes')}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--session-source', choices=('host-archive', 'launch-receipts'), default='host-archive')
    args = parser.parse_args()
    export(args.directory, args.meta_key, args.session_source)


if __name__ == '__main__':
    main()
