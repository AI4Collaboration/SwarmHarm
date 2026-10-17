import argparse
import concurrent.futures
import hashlib
import json
import time
import threading
from pathlib import Path

from cloud import SESSION, save


def retrieve(directory, settings, exports, bindings=None):
    storages = {edge['node']['id']: edge['node'] for edge in settings['dataStorages']['edges']}
    s3 = SESSION.client('s3')
    jobs = []
    coverage = []
    nodes = {}
    listing_jobs = set()
    ledger_lock = threading.Lock()
    for index, export in enumerate(exports):
        for edge in export['requests']['edges']:
            request = edge['node']
            project = request['projectID'].rsplit('/', 1)[-1]
            request_id = request['id'].rsplit('/', 1)[-1]
            prefix = f'{project}/requests/{request_id}'
            storage = storages[request['dataStorageID'] or settings['defaultDataStorageID']]
            assert storage['type'] == 's3', storage['type']
            link = {'subject_index': index, 'request_id': request['id'], 'status': request['status'],
                    'model': request['modelID'], 'channel_id': request['channelID']}
            if bindings:
                link.update(bindings[index])
            coverage.append(link)
            objects = [(prefix, request, None)]
            for execution in request['executions']['edges']:
                node = execution['node']
                objects.append((f'{prefix}/executions/{node["id"].rsplit("/", 1)[-1]}', node, node['id']))
            for base, node, execution_id in objects:
                node_storage = storages[node.get('dataStorageID') or request['dataStorageID'] or settings['defaultDataStorageID']]
                node_bucket = node_storage['settings']['s3']['bucketName']
                nodes[(node_bucket, base)] = {**link, 'execution_id': execution_id, 'payload_status': node['status']}
                listing_jobs.add((node_bucket, prefix + '/'))
                for name, field in [('request_body', 'requestBody'), ('response_body', 'responseBody'), ('response_chunks', 'responseChunks')]:
                    required = name == 'request_body' or (node['status'] == 'completed' and (name != 'response_chunks' or node.get('stream', request['stream'])))
                    if required or node[field]:
                        jobs.append((node_bucket, f'{base}/{name}.json', {**link, 'execution_id': execution_id, 'kind': name, 'payload_status': node['status']}))

    def list_payloads(job):
        bucket, prefix = job
        pages = list(s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix))
        return {'bucket': bucket, 'prefix': prefix, 'pages': len(pages),
            'objects': [{'key': item['Key'], 'bytes': item['Size']} for page in pages for item in page.get('Contents', [])]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        listings = list(pool.map(list_payloads, sorted(listing_jobs)))
    available = {}
    for listing in listings:
        for item in listing['objects']:
            base, filename = item['key'].rsplit('/', 1)
            if filename in ('request_body.json', 'response_body.json', 'response_chunks.json'):
                link = nodes[(listing['bucket'], base)]
                available[(listing['bucket'], item['key'])] = {**link, 'kind': filename.removesuffix('.json')}
    assert {(bucket, key) for bucket, key, _ in jobs} <= available.keys()
    jobs = [(bucket, key, link) for (bucket, key), link in sorted(available.items())]
    save(directory, 'stored-object-listings.json', listings)
    previous_path = directory / 'recording-receipts.json'
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {'receipts': [], 's3_get_requests': 0, 's3_list_requests': 0}
    existing = {(row['bucket'], row['object_key']): row for row in previous['receipts']}
    downloads = []

    def download(job):
        bucket, key, link = job
        target = directory / 'stored-payloads' / key
        target.parent.mkdir(parents=True, exist_ok=True)
        if (bucket, key) in existing:
            receipt = existing[(bucket, key)]
            raw = target.read_bytes()
            assert len(raw) == receipt['bytes'] and hashlib.sha256(raw).hexdigest() == receipt['sha256']
            return {**receipt, **link}
        response = s3.get_object(Bucket=bucket, Key=key)
        with response['Body'] as body:
            raw = body.read()
        target.write_bytes(raw)
        decoded = json.loads(raw)
        assert decoded or link['payload_status'] != 'completed', key
        receipt = {**link, 'bucket': bucket, 'object_key': key, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'json_nonempty': bool(decoded), 's3_request_id': response['ResponseMetadata']['RequestId']}
        with ledger_lock:
            downloads.append(key)
            with (directory / 'retrieval-ledger.jsonl').open('a') as ledger:
                ledger.write(json.dumps({'time': time.time(), **receipt}) + '\n')
        return receipt

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(download, jobs))
    report = {'time': time.time(), 'requests': len(coverage), 'objects': len(receipts),
              'bytes': sum(row['bytes'] for row in receipts), 'coverage': coverage, 'receipts': receipts,
              's3_get_requests': previous['s3_get_requests'] + len(downloads),
              's3_list_requests': previous.get('s3_list_requests', 0) + sum(row['pages'] for row in listings),
              's3_storage_gib': sum(row['bytes'] for row in receipts) / 2**30,
              'cost_basis': 'S3 retrieval count and stored bytes; account billing determines actual charges'}
    save(directory, 'recording-receipts.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    settings = json.loads((args.directory / 'recording-settings.json').read_text())
    binding = json.loads((args.directory / 'binding.json').read_text())
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    exports = [json.loads((args.directory / f'gateway-{index}.json').read_text()) for index in range(len(binding['hosts']))]
    links = []
    for index, host in enumerate(binding['hosts']):
        goals = json.loads((args.directory / host['id'] / 'var/lib/peer-operator/native-goals.json').read_text())['goals']
        key = json.loads((args.directory / f'private-key-{index}.json').read_text())
        links.append({'instance_id': host['id'], 'api_key_id': key['id'], 'session_id': goals[0]['thread_id'],
            'repeat': binding['repeat'], 'issue': cloud['issue'], 'case': f'N{len(binding["hosts"])}-K{len(host["seeds"])}'})
    report = retrieve(args.directory, settings, exports, links)
    print(json.dumps({key: value for key, value in report.items() if key not in ('coverage', 'receipts')}))


if __name__ == '__main__':
    main()
