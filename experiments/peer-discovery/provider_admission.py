import argparse
import concurrent.futures
import json
import threading
import time
from pathlib import Path

import requests

from cloud import save
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--issue', required=True)
    args = parser.parse_args()
    key = gateway(args.meta_key, 'create', f'{args.issue.lower()}-provider-{args.directory.name}')
    save(args.directory, 'private-key-0.json', key)
    barrier = threading.Barrier(8)

    def call(index):
        barrier.wait(timeout=30)
        started = time.time_ns()
        response = requests.post('https://lmportal.iefbr14.xyz/v1/responses',
            headers={'Authorization': 'Bearer ' + key['key']},
            json={'model': 'gpt-6-luna', 'instructions': 'Reply with OK.',
                  'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'Reply with OK.'}]}],
                  'reasoning': {'effort': 'xhigh'}, 'store': False, 'stream': True}, timeout=120)
        (args.directory / f'response-{index}.txt').write_bytes(response.content)
        return {'index': index, 'started_ns': started, 'finished_ns': time.time_ns(),
                'http_status': response.status_code}

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            calls = list(pool.map(call, range(8)))
        save(args.directory, 'calls.json', calls)
        metadata = gateway(args.meta_key, 'export', key['id'])
        save(args.directory, 'gateway.json', metadata)
        records = [edge['node'] for edge in metadata['requests']['edges']]
        completed = [record for record in records if record['status'] == 'completed']
        result = {'checked_at': time.time(), 'api_key_id': key['id'], 'requests': len(records),
                  'completed_requests': len(completed), 'http_statuses': [call['http_status'] for call in calls],
                  'elapsed_seconds': (max(call['finished_ns'] for call in calls)
                                      - min(call['started_ns'] for call in calls)) / 1e9,
                  'upstream_models': sorted({execution['node']['upstreamModelID'] for record in completed
                      for execution in record['executions']['edges'] if execution['node']['status'] == 'completed'}),
                  'quota_usage': metadata['apiKeyQuotaUsages']}
        save(args.directory, 'provider-admission.json', result)
        print(json.dumps(result), flush=True)
        assert len(completed) == 8 and all(call['http_status'] == 200 for call in calls)
        assert result['upstream_models'] == ['gpt-6-luna']
        assert all(record['reasoningEffort'] == 'xhigh' for record in records)
    finally:
        revoked = gateway(args.meta_key, 'disable', key['id'])
        assert revoked['updateAPIKeyStatus']['status'] == 'disabled'
        save(args.directory, 'key-revocation-0.json', revoked)


if __name__ == '__main__':
    main()
