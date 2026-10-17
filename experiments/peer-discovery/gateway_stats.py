import argparse
import collections
import datetime
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    metadata = [json.loads(path.read_text()) for path in args.directory.glob('gateway-*.json')]
    requests = [edge['node'] for data in metadata for edge in data['requests']['edges']]
    usages = [edge['node'] for request in requests for edge in request['usageLogs']['edges']]
    first = [min(datetime.datetime.fromisoformat(edge['node']['createdAt'].replace('Z', '+00:00')).timestamp()
                 for edge in data['requests']['edges']) for data in metadata if data['requests']['edges']]
    result = {'keys': len(metadata), 'keys_with_requests': len(first), 'requests': len(requests),
              'request_states': dict(collections.Counter(request['status'] for request in requests)),
              'total_tokens': sum(usage['totalTokens'] for usage in usages),
              'upstream_models': sorted({edge['node']['upstreamModelID'] for request in requests for edge in request['executions']['edges']}),
              'reasoning_efforts': sorted({request['reasoningEffort'] for request in requests})}
    if first:
        result['first_request_skew_seconds'] = max(first) - min(first)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
