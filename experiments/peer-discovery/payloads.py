import concurrent.futures
import hashlib
import json
import threading
from pathlib import Path

from botocore.config import Config

from cloud import SESSION, save


def collect_payloads(directory):
    policy = json.loads((directory / 'recording-policy.json').read_text())
    storage = next(edge['node'] for edge in policy['dataStorages']['edges']
                   if edge['node']['id'] == policy['defaultDataStorageID'])
    assert storage['type'] == 's3'
    settings = storage['settings']['s3']
    client = SESSION.client('s3', region_name=settings['region'],
        endpoint_url=settings['endpoint'] or None,
        config=Config(connect_timeout=10, read_timeout=60, max_pool_connections=16,
                      s3={'addressing_style': 'path' if settings['pathStyle'] else 'auto'}))
    calls = {'GetObject': 0, 'HeadObject': 0}
    call_lock = threading.Lock()

    def count_call(model, **kwargs):
        with call_lock:
            calls[model.name] += 1

    for operation in calls:
        client.meta.events.register(f'before-call.s3.{operation}', count_call)
    binding = json.loads((directory / 'binding.json').read_text())
    jobs = []
    requests = []
    for index, host in enumerate(binding['hosts']):
        key = json.loads((directory / f'private-key-{index}.json').read_text())
        project_id = key['project_id'].rsplit('/', 1)[1]
        exported = json.loads((directory / f'gateway-{index}.json').read_text())
        goals = json.loads((directory / host['id'] / 'var/lib/peer-operator/native-goals.json').read_text())
        for edge in exported['requests']['edges']:
            request = edge['node']
            request_id = request['id'].rsplit('/', 1)[1]
            prefix = f'{project_id}/requests/{request_id}'
            link = {'instance_id': host['id'], 'api_key_id': key['id'], 'request_id': request['id'],
                    'session_ids': [goal['thread_id'] for goal in goals['goals']],
                    'repeat': binding['repeat'], 'status': request['status'], 'issue': binding['issue']}
            requests.append(link)
            entities = [(prefix, request, None)]
            entities.extend((f'{prefix}/executions/{item["node"]["id"].rsplit("/", 1)[1]}',
                             item['node'], item['node']['id']) for item in request['executions']['edges'])
            for location, entity, execution_id in entities:
                for name, field in (('request_body', 'requestBody'), ('response_body', 'responseBody'), ('response_chunks', 'responseChunks')):
                    jobs.append((f'{location}/{name}.json', {**link, 'execution_id': execution_id,
                                 'field': field, 'entity_status': entity['status']}))
    assert requests

    def retrieve(job):
        object_key, link = job
        destination = directory / 'stored-payloads' / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(settings['bucketName'], object_key, str(destination))
        raw = destination.read_bytes()
        payload = json.loads(raw)
        if link['entity_status'] == 'completed' or link['field'] == 'requestBody':
            assert payload, object_key
        return {**link, 'bucket': settings['bucketName'], 'object_key': object_key,
                'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        receipts = list(pool.map(retrieve, jobs))
    report = {'request_count': len(requests), 'object_count': len(receipts),
              'bytes': sum(row['bytes'] for row in receipts), 'requests': requests, 'objects': receipts,
              's3_get_requests': calls['GetObject'], 's3_head_requests': calls['HeadObject'],
              'storage_bucket': settings['bucketName']}
    save(directory, 'recording-receipts.json', report)
    return report
