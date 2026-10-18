import collections
import concurrent.futures
import json
from pathlib import Path
import sys
import time

from remote import BASE

sys.path.insert(0, str(BASE / 'operator-code/experiments/peer-discovery'))
from cloud import save
from repeat import gateway


def main():
    directory = BASE / f'repeat-{int(sys.argv[1])}'
    meta = Path('/home/cpt-llm/Playground/cpt-llm-agent-workspace/swarmharm-dd7d0eb4a945/swh-78-068357cad047/workdir/private/swh6-ed25519')
    stamp = str(time.time_ns())
    destination = directory / 'live-gateway' / stamp

    def export(index):
        key = json.loads((directory / f'private-key-{index}.json').read_text())
        result = gateway(meta, 'export', key['id'])
        save(destination, f'gateway-{index}.json', result)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        exports = list(pool.map(export, range(32)))
    requests = [edge['node'] for exported in exports for edge in exported['requests']['edges']]
    executions = [edge['node'] for request in requests for edge in request['executions']['edges']]
    report = {'observed_at': time.time(), 'requests': len(requests),
        'tokens': sum(edge['node']['totalTokens'] for request in requests for edge in request['usageLogs']['edges']),
        'request_states': dict(collections.Counter(row['status'] for row in requests)),
        'execution_status_codes': dict(collections.Counter(str(row['responseStatusCode']) for row in executions))}
    save(destination, 'summary.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
