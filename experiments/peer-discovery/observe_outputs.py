import argparse
import concurrent.futures
import json
import time
from pathlib import Path

from cloud import ROOT, save, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_bytes())

    def observe(host):
        result = ssh(args.directory, host['public_ip'], 'sudo python3 -', (ROOT / 'host_outputs.py').read_bytes())
        return {'instance_id': host['id'], **json.loads(result.stdout)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(observe, binding['hosts']))
    now = time.time()
    save(args.directory, f'output-observations-{int(now)}.json', {'observed_at': now, 'hosts': rows})
    print(json.dumps({'subjects': len(rows), 'submitted_files': sum('/home/agent/discovered_peers.json' in row['files'] for row in rows),
        'frozen_files': sum('/var/lib/peer-operator/frozen-output.json' in row['files'] for row in rows)}))


if __name__ == '__main__':
    main()
