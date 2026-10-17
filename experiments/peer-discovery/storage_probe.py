import argparse
import hashlib
import json
from pathlib import Path

from cloud import SESSION, save
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--key-id', required=True)
    args = parser.parse_args()
    policy = gateway(args.meta_key, 'recording', '')
    assert all(policy['storagePolicy'][name] for name in ('storeRequestBody', 'storeResponseBody', 'storeChunks'))
    storage = next(edge['node'] for edge in policy['dataStorages']['edges']
                   if edge['node']['id'] == policy['defaultDataStorageID'])
    assert storage['type'] == 's3'
    settings = storage['settings']['s3']
    requests = gateway(args.meta_key, 'export', args.key_id)
    request = next(edge['node'] for edge in requests['requests']['edges'] if edge['node']['status'] == 'completed')
    assert request['dataStorageID'] == storage['id']
    request_id = request['id'].rsplit('/', 1)[1]
    project_id = request['projectID'].rsplit('/', 1)[1]
    prefix = f'{project_id}/requests/{request_id}'
    keys = [f'{prefix}/{name}.json' for name in ('request_body', 'response_body', 'response_chunks')]
    for edge in request['executions']['edges']:
        execution_id = edge['node']['id'].rsplit('/', 1)[1]
        keys.extend(f'{prefix}/executions/{execution_id}/{name}.json'
                    for name in ('request_body', 'response_body', 'response_chunks'))
    client = SESSION.client('s3', region_name=settings['region'], endpoint_url=settings['endpoint'] or None)
    receipts = []
    for key in keys:
        path = args.directory / 'stored-payloads' / key
        path.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(settings['bucketName'], key, str(path))
        raw = path.read_bytes()
        assert json.loads(raw)
        receipts.append({'object_key': key, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    save(args.directory, 'storage-probe.json', {'policy': policy, 'api_key_id': args.key_id,
         'request': request, 'receipts': receipts})
    print(json.dumps({'request_id': request['id'], 'objects': len(receipts),
                      'bytes': sum(row['bytes'] for row in receipts)}))


if __name__ == '__main__':
    main()
