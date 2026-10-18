import argparse
from collections import Counter
import concurrent.futures
import json
import time
from pathlib import Path

from cloud import ROOT, save, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--stage', required=True)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    def inspect(host):
        response = ssh(args.directory, host['public_ip'], 'sudo python3 -',
                       (ROOT / 'observe_host.py').read_bytes())
        return {'instance_id': host['id'], **json.loads(response.stdout)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, binding['hosts']))
    result = {'time': time.time(), 'stage': args.stage, 'subjects': len(rows),
        'goal_states': dict(Counter(goal['status'] for row in rows for goal in row.get('native_goals', []))),
        'live_output_subjects': sum('live_output' in row for row in rows),
        'frozen_output_subjects': sum('frozen_output' in row for row in rows), 'rows': rows}
    save(args.directory, f'observation-{args.stage}.json', result)
    print(json.dumps({key: value for key, value in result.items() if key != 'rows'}))


if __name__ == '__main__':
    main()
