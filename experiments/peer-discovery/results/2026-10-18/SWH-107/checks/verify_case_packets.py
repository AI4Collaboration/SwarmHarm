import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--harness', type=Path, required=True)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    def inspect(host):
        capture = args.directory / host['id'] / 'var/lib/peer-operator/traffic.pcap'
        result = subprocess.run([sys.executable, str(args.harness / 'verify_packets.py'), str(capture)],
                                capture_output=True, text=True, check=True)
        return {'instance_id': host['id'], **json.loads(result.stdout)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(inspect, binding['hosts']))
    result = {'repeat': binding['repeat'], 'verified_captures': len(rows),
              'verified_packets': sum(row['packets'] for row in rows), 'rows': rows}
    target = args.directory.parent / f'packet-decoders-repeat-{binding["repeat"]}.json'
    target.write_text(json.dumps(result, indent=2))
    print(json.dumps({name: value for name, value in result.items() if name != 'rows'}))


if __name__ == '__main__':
    main()
