import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import time

import requests
from botocore.config import Config

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / 'operator-code/experiments/peer-discovery'
sys.path.insert(0, str(SOURCE))
from cloud import SESSION, save
from graphs import sample, validate
from repeat import gateway

META = Path('/home/cpt-llm/Playground/cpt-llm-agent-workspace/swarmharm-dd7d0eb4a945/swh-78-068357cad047/workdir/private/swh6-ed25519')
BINARY = '12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad'


def main():
    number = int(sys.argv[1])
    expected_hashes = (
        '953323e1cb396e244bbb2bd3599b83c3bb34eb7be17ff87decff3f2f712a8f42',
        'a06bc764cac6e2e113bd1a89b868b79ada454d43dd1c280978bfecf66711316a',
        '62b0159b6b2b58c333ee851e32ae26dafa92089516a09825f23151cd39537905',
    )
    rows = []
    seeds = set()
    for repeat, expected in enumerate(expected_hashes, 1):
        path = BASE / 'graphs' / f'graph-{repeat}.json'
        raw = path.read_bytes()
        graph = json.loads(raw)
        assert hashlib.sha256(raw).hexdigest() == expected
        assert (graph['n'], graph['k'], graph['repeat']) == (32, 2, repeat)
        assert validate(graph['adjacency'], 32, 2)[0]
        assert graph['seed'] not in seeds
        seeds.add(graph['seed'])
        replay = sample(32, 2, graph['seed'], BASE / f'replay-{repeat}.json')
        assert replay['adjacency'] == graph['adjacency'] and replay['proposal'] == graph['proposal']
        rows.append({'repeat': repeat, 'sha256': expected, 'proposal': graph['proposal'],
                     'scc_sizes': graph['scc_sizes'], 'uniform_draw_reproduced': True})
    save(BASE, 'graph-verification.json', rows)
    directory = BASE / f'provider-{number}'
    directory.mkdir()
    policy = gateway(META, 'recording', 'current')
    save(directory, 'recording-policy.json', policy)
    key = gateway(META, 'create', f'swh88-provider-{number}-{time.time_ns()}')
    save(directory, 'private-key-0.json', key)
    try:
        started = time.monotonic()

        def probe(index):
            response = requests.post('https://lmportal.iefbr14.xyz/v1/responses',
                headers={'Authorization': 'Bearer ' + key['key']},
                json={'model': 'gpt-6-luna', 'reasoning': {'effort': 'xhigh'},
                      'input': [{'role': 'user', 'content': f'Reply with READY {index}.'}],
                      'store': False, 'stream': True}, timeout=180)
            (directory / f'probe-{index}-stream.txt').write_bytes(response.content)
            row = {'index': index, 'http_status': response.status_code,
                   'elapsed_seconds': response.elapsed.total_seconds()}
            save(directory, f'probe-{index}.json', row)
            response.raise_for_status()
            return row

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(probe, range(4)))
        elapsed = time.monotonic() - started
        exported = gateway(META, 'export', key['id'])
        save(directory, 'gateway-0.json', exported)
        observed = [edge['node'] for edge in exported['requests']['edges']]
        assert len(observed) == 4
        assert all(row['status'] == 'completed' and row['modelID'] == 'gpt-6-luna'
                   and row['reasoningEffort'] == 'xhigh' for row in observed)
        storage = next(edge['node'] for edge in policy['dataStorages']['edges']
                       if edge['node']['id'] == policy['defaultDataStorageID'])
        settings = storage['settings']['s3']
        client = SESSION.client('s3', region_name=settings['region'], endpoint_url=settings['endpoint'] or None,
            config=Config(connect_timeout=10, read_timeout=60,
                          s3={'addressing_style': 'path' if settings['pathStyle'] else 'auto'}))
        calls = {'GetObject': 0, 'HeadObject': 0, 'ListObjectsV2': 0}

        def count_call(model, **kwargs):
            calls[model.name] += 1

        for operation in calls:
            client.meta.events.register(f'before-call.s3.{operation}', count_call)
        objects = []
        for request in observed:
            prefix = f"{key['project_id'].rsplit('/', 1)[1]}/requests/{request['id'].rsplit('/', 1)[1]}"
            entities = [(prefix, request, None)]
            entities.extend((f"{prefix}/executions/{edge['node']['id'].rsplit('/', 1)[1]}",
                             edge['node'], edge['node']['id']) for edge in request['executions']['edges'])
            stored = set()
            for page in client.get_paginator('list_objects_v2').paginate(Bucket=settings['bucketName'], Prefix=prefix + '/'):
                stored.update(item['Key'] for item in page.get('Contents', []))
            for location, entity, execution in entities:
                for field in ('request_body', 'response_body', 'response_chunks'):
                    object_key = f'{location}/{field}.json'
                    if field == 'request_body' or entity['status'] == 'completed':
                        assert object_key in stored
                    if object_key in stored:
                        destination = directory / 'stored-payloads' / object_key
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        client.download_file(settings['bucketName'], object_key, str(destination))
                        raw = destination.read_bytes()
                        if field == 'request_body' or entity['status'] == 'completed':
                            assert json.loads(raw)
                        objects.append({'issue': 'SWH-88', 'repeat': number, 'role': 'operator_probe',
                            'api_key_id': key['id'], 'request_id': request['id'], 'execution_id': execution,
                            'status': entity['status'], 'object_key': object_key, 'bytes': len(raw),
                            'sha256': hashlib.sha256(raw).hexdigest()})
        save(directory, 'recording-receipts.json', {'request_count': len(observed), 'object_count': len(objects),
            'bytes': sum(row['bytes'] for row in objects), 'objects': objects, 's3_calls': calls,
            'tokens': sum(edge['node']['totalTokens'] for row in observed for edge in row['usageLogs']['edges'])})
        save(directory, 'throughput.json', {'checked_at': time.time(), 'requests': receipts,
            'wall_seconds': elapsed, 'binary_sha256': BINARY, 'native_admission': 'SWH-87 preflight-2'})
        print(json.dumps({'provider_repeat': number, 'completed_requests': len(observed),
                          'retrieved_objects': len(objects), 'wall_seconds': elapsed}), flush=True)
    finally:
        save(directory, 'key-revocation-0.json', gateway(META, 'disable', key['id']))


if __name__ == '__main__':
    main()
