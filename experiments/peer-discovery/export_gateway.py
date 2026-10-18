import argparse
import json
from pathlib import Path

from cloud import save
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    args = parser.parse_args()
    binding = json.loads((args.source / 'binding.json').read_text())
    count = 0
    for index, host in enumerate(binding['hosts']):
        key = json.loads((args.source / f'private-key-{index}.json').read_text())
        data = gateway(args.meta_key, 'export', key['id'])
        save(args.output, f'gateway-{index}.json', data)
        count += len(data['requests']['edges'])
    print(json.dumps({'keys': len(binding['hosts']), 'requests': count}))


if __name__ == '__main__':
    main()
