import argparse
import concurrent.futures
import json
from pathlib import Path
import time

from cloud import ROOT, save, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    release = json.loads((args.directory / 'release.json').read_text())
    def inspect(host):
        result = ssh(args.directory, host['public_ip'], 'sudo python3 -', (ROOT / 'snapshot.py').read_bytes())
        return {'instance_id': host['id'], **json.loads(result.stdout)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, binding['hosts']))
    stamp = time.time_ns()
    save(args.directory / 'operator-observations', f'{stamp}.json', rows)
    print(json.dumps({'repeat': binding['repeat'], 'subjects': len(rows),
        'seconds_since_release': time.time() - release['T_start'],
        'invocations': sum(len(row['receipts']['launch_markers']) for row in rows),
        'accepted_goals': sum(bool(row['receipts'].get('native-goals', {}).get('goals')) for row in rows),
        'output_files': sum('output_bytes' in row['receipts'] for row in rows),
        'minimum_available_memory_bytes': min(row['receipts']['resources']['memory_available_bytes'] for row in rows),
        'minimum_free_disk_bytes': min(row['receipts']['resources']['disk_free_bytes'] for row in rows),
        'stopped_subjects': sum('process-stop' in row['receipts'] for row in rows)}))


if __name__ == '__main__':
    main()
