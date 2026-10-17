import argparse
import json
import time
from pathlib import Path

from cloud import save
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    ids = [json.loads((args.directory / f'private-key-{index}.json').read_text())['id'] for index in range(len(binding['hosts']))]
    rows = gateway(args.meta_key, 'progress', json.dumps(ids))
    report = {'observed_at': time.time(), 'subjects': len(ids), 'rows': rows}
    save(args.directory, f'gateway-progress-{int(report["observed_at"])}.json', report)
    print(json.dumps({'subjects': len(ids), 'keys_with_requests': sum(bool(row['requests']['edges']) for row in rows),
        'requests': sum(row['requests']['totalCount'] for row in rows),
        'tokens': sum(quota['usage']['totalTokens'] for row in rows for quota in row['quota'])}))


if __name__ == '__main__':
    main()
