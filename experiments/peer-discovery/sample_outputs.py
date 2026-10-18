import argparse
import base64
import concurrent.futures
import json
from pathlib import Path

from cloud import ROOT, save, ssh
from grade import grade


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--stage', required=True)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    ips = [host['public_ip'] for host in binding['hosts']]
    def inspect(host):
        response = ssh(args.directory, host['public_ip'], 'sudo python3 -', (ROOT / 'output_state.py').read_bytes())
        result = json.loads(response.stdout)
        result['instance_id'] = host['id']
        for name, file in result['files'].items():
            raw = base64.b64decode(file['bytes_base64'], validate=True)
            file['score'] = grade(raw, host['public_ip'], ips, host['seeds'])
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, binding['hosts']))
    result = {'stage': args.stage, 'subjects': len(rows), 'observations': rows,
              'home_outputs': sum('home' in row['files'] for row in rows),
              'frozen_outputs': sum('frozen' in row['files'] for row in rows)}
    save(args.directory, f'output-observation-{args.stage}.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'observations'}))


if __name__ == '__main__':
    main()
