import argparse
import concurrent.futures
import json
from pathlib import Path

from cloud import ROOT, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda host: ssh(args.directory, host['public_ip'], 'sudo python3 -',
            (ROOT / 'clock_correction.py').read_bytes()), binding['hosts']))
        collected = list(pool.map(lambda host: ssh(args.directory, host['public_ip'], 'sudo python3 -',
            (ROOT / 'collect.py').read_bytes()), binding['hosts']))
    print(json.dumps([json.loads(result.stdout) for result in results]))
    print(json.dumps([json.loads(result.stdout) for result in collected]))


if __name__ == '__main__':
    main()
