import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('graph', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).parent
    count = json.loads(args.graph.read_text())['n']
    preparation_deadline = time.monotonic() + 1800
    while len(list(args.directory.glob('*-timer.json'))) < count:
        assert time.monotonic() < preparation_deadline
        assert not (args.directory / 'cleanup.json').exists()
        time.sleep(5)
    release = json.loads((args.directory / 'release.json').read_text())
    assert time.time() < release['T_start'] - 10
    subprocess.run([sys.executable, str(root / 'verify_release.py'), str(args.directory), str(args.graph)], check=True)
    assert time.time() < release['T_start']
    print(json.dumps({'release_verified_before_start': True, **release}), flush=True)
    offsets = [-5, 20, 300, 600, 900, 1200, 1500, release['allowance_seconds'] - 15]
    for offset in offsets:
        target = release['T_start'] + offset
        while time.time() < target:
            time.sleep(min(5, target - time.time()))
        command = [sys.executable, str(root / 'snapshot.py'), str(args.directory), '--meta-key', str(args.meta_key)]
        if offset >= 0:
            command.append('--hosts')
        subprocess.run(command, check=True)
        print(json.dumps({'observed_offset_seconds': offset, 'time': time.time()}), flush=True)


if __name__ == '__main__':
    main()
