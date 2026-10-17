import argparse
import concurrent.futures
import json
import threading
import time
from pathlib import Path

import requests

from cloud import save
from recording import retrieve
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--issue', required=True)
    args = parser.parse_args()
    directory = args.directory
    assert not directory.exists()
    directory.mkdir(parents=True)
    settings = gateway(args.meta_key, 'recording', '')
    save(directory, 'recording-settings.json', settings)
    key = gateway(args.meta_key, 'create', f'{args.issue.lower()}-provider-probe-{int(time.time())}')
    save(directory, 'private-key-0.json', key)
    barrier = threading.Barrier(2)

    def call(index):
        if index < 2:
            barrier.wait(timeout=10)
        started = time.time()
        response = requests.post('https://lmportal.iefbr14.xyz/v1/responses',
            headers={'Authorization': 'Bearer ' + key['key']},
            json={'model': 'gpt-6-luna', 'instructions': 'Reply with OK.',
                'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'Reply with OK.'}]}],
                'reasoning': {'effort': 'xhigh'}, 'store': False, 'stream': True}, timeout=120)
        row = {'index': index, 'started': started, 'ended': time.time(),
            'http_status': response.status_code, 'body': response.text}
        save(directory, f'response-{index}.json', row)
        response.raise_for_status()
        return {name: value for name, value in row.items() if name != 'body'}

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(call, range(2)))
        rows.append(call(2))
    finally:
        save(directory, 'key-revocation-0.json', gateway(args.meta_key, 'disable', key['id']))
        export = gateway(args.meta_key, 'export', key['id'])
        save(directory, 'gateway-0.json', export)
        retrieve(directory, settings, [export], [{'issue': args.issue, 'purpose': 'provider-admission',
            'api_key_id': key['id']}])
    requests_exported = [edge['node'] for edge in export['requests']['edges']]
    assert len(requests_exported) == 3
    assert all(request['status'] == 'completed' for request in requests_exported)
    for request in requests_exported:
        completed = [edge['node'] for edge in request['executions']['edges'] if edge['node']['status'] == 'completed']
        assert completed and all(execution['upstreamModelID'] == 'gpt-6-luna'
            and execution['reasoningEffort'] == 'xhigh' for execution in completed)
    save(directory, 'provider-admission.json', {'issue': args.issue, 'model': 'gpt-6-luna',
        'reasoning': 'xhigh', 'simultaneous_probe_requests': 2, 'requests': rows,
        'completed_gateway_requests': len(requests_exported)})
    print(json.dumps(rows), flush=True)


if __name__ == '__main__':
    main()
