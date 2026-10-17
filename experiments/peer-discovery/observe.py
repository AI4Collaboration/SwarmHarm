import argparse
import concurrent.futures
import json
from pathlib import Path

from cloud import ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())

    def observe(host):
        result = ssh(args.directory, host['public_ip'], 'sudo cat /var/lib/peer-operator/native-goals.json', check=False)
        if result.returncode:
            return {'instance_id': host['id'], 'observation': 'initializing'}
        body = json.loads(result.stdout)
        goal = body['goals'][0]
        return {'instance_id': host['id'], 'status': goal['status'], 'tokens_used': goal['tokens_used'],
            'time_used_seconds': goal['time_used_seconds']}

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        print(json.dumps(list(pool.map(observe, binding['hosts'])), indent=2))


if __name__ == '__main__':
    main()
