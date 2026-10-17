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
    ledger_lock = threading.Lock()
    for index, export in enumerate(exports):
        for edge in export['requests']['edges']:
            request = edge['node']
            project = request['projectID'].rsplit('/', 1)[-1]
            request_id = request['id'].rsplit('/', 1)[-1]
            prefix = f'{project}/requests/{request_id}'
            storage = storages[request['dataStorageID'] or settings['defaultDataStorageID']]
            assert storage['type'] == 's3', storage['type']
            bucket = storage['settings']['s3']['bucketName']
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
                for name, field in [('request_body', 'requestBody'), ('response_body', 'responseBody'), ('response_chunks', 'responseChunks')]:
                    required = name == 'request_body' or (node['status'] == 'completed' and (name != 'response_chunks' or request['stream']))
                    if required or node[field]:
                        jobs.append((bucket, f'{base}/{name}.json', {**link, 'execution_id': execution_id, 'kind': name}))

    def download(job):
        bucket, key, link = job
        target = directory / 'stored-payloads' / key
        target.parent.mkdir(parents=True, exist_ok=True)
        response = s3.get_object(Bucket=bucket, Key=key)
        with response['Body'] as body:
            raw = body.read()
        target.write_bytes(raw)
        assert json.loads(raw), key
        receipt = {**link, 'bucket': bucket, 'object_key': key, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 's3_request_id': response['ResponseMetadata']['RequestId']}
        with ledger_lock:
            with (directory / 'retrieval-ledger.jsonl').open('a') as ledger:
                ledger.write(json.dumps({'time': time.time(), **receipt}) + '\n')
        return receipt

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(download, jobs))
    report = {'time': time.time(), 'requests': len(coverage), 'objects': len(receipts),
              'bytes': sum(row['bytes'] for row in receipts), 'coverage': coverage, 'receipts': receipts,
              's3_get_requests': len(receipts), 's3_storage_gib': sum(row['bytes'] for row in receipts) / 2**30,
              'cost_basis': 'S3 retrieval count and stored bytes; account billing determines actual charges'}
    save(directory, 'recording-receipts.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    settings = json.loads((args.directory / 'recording-settings.json').read_text())
    binding = json.loads((args.directory / 'binding.json').read_text())
    exports = [json.loads((args.directory / f'gateway-{index}.json').read_text()) for index in range(len(binding['hosts']))]
    links = []
    for index, host in enumerate(binding['hosts']):
        goals = json.loads((args.directory / host['id'] / 'var/lib/peer-operator/native-goals.json').read_text())['goals']
        key = json.loads((args.directory / f'private-key-{index}.json').read_text())
        links.append({'instance_id': host['id'], 'api_key_id': key['id'], 'session_id': goals[0]['thread_id'], 'repeat': binding['repeat']})
    report = retrieve(args.directory, settings, exports, links)
    print(json.dumps({key: value for key, value in report.items() if key not in ('coverage', 'receipts')}))


if __name__ == '__main__':
    main()
