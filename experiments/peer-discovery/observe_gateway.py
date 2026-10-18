import argparse
from collections import Counter
import json
import time
from pathlib import Path

from cloud import save
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--stage', required=True)
    parser.add_argument('--indices', nargs='+', type=int, required=True)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    rows = []
    requests = []
    executions = []
    for index in args.indices:
        key_id = json.loads((args.directory / f'private-key-{index}.json').read_text())['id']
        data = gateway(args.meta_key, 'recording-export', key_id)
        rows.append({'index': index, 'instance_id': binding['hosts'][index]['id'],
                     'key_id': key_id, 'metadata': data})
        requests.extend(edge['node'] for edge in data['requests']['edges'])
    executions = [edge['node'] for request in requests for edge in request['executions']['edges']]
    result = {'time': time.time(), 'stage': args.stage, 'sampled_subjects': len(rows),
        'sampled_indices': args.indices, 'requests': len(requests),
        'client_states': dict(Counter(request['status'] for request in requests)),
        'execution_states': dict(Counter(execution['status'] for execution in executions)),
        'upstream_http_status': dict(Counter(str(execution['responseStatusCode']) for execution in executions)),
        'total_tokens': sum(edge['node']['totalTokens'] for request in requests
                            for edge in request['usageLogs']['edges']),
        'rows': rows}
    save(args.directory, f'observation-gateway-{args.stage}.json', result)
    print(json.dumps({key: value for key, value in result.items() if key != 'rows'}))


if __name__ == '__main__':
    main()
