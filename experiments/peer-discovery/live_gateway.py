import argparse
import concurrent.futures
import json
from pathlib import Path

from cloud import save
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--stage', required=True)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    def inspect(pair):
        index, host = pair
        key = json.loads((args.directory / f'private-key-{index}.json').read_text())
        result = gateway(args.meta_key, 'recording-export', key['id'])
        save(args.directory, f'gateway-live-{args.stage}-{index}.json', result)
        requests = [edge['node'] for edge in result['requests']['edges']]
        executions = [edge['node'] for request in requests for edge in request['executions']['edges']]
        usage = result['apiKeyQuotaUsages']
        return {'instance_id': host['id'], 'api_key_id': key['id'], 'requests': len(requests),
                'first_request': min(request['createdAt'] for request in requests) if requests else None,
                'request_models': sorted({request['modelID'] for request in requests}),
                'upstream_models': sorted({execution['upstreamModelID'] for execution in executions}),
                'channels': sorted({execution['channelID'] for execution in executions}),
                'reasoning': sorted({request['reasoningEffort'] for request in requests}),
                'quota_usage': usage}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(inspect, enumerate(binding['hosts'])))
    result = {'stage': args.stage, 'subjects': len(rows), 'rows': rows,
              'subjects_with_requests': sum(row['requests'] > 0 for row in rows),
              'requests': sum(row['requests'] for row in rows),
              'quota_tokens': sum(usage['usage']['totalTokens'] for row in rows for usage in row['quota_usage']),
              'upstream_models': sorted({model for row in rows for model in row['upstream_models']}),
              'channels': sorted({channel for row in rows for channel in row['channels']})}
    save(args.directory, f'gateway-live-{args.stage}.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'rows'}))


if __name__ == '__main__':
    main()
