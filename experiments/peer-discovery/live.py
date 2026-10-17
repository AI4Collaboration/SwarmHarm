import argparse
import collections
import concurrent.futures
import json
import time
from pathlib import Path

from cloud import ROOT, save, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    release = json.loads((args.directory / 'release.json').read_text())
    def observe(host):
        result = ssh(args.directory, host['public_ip'], 'sudo python3 -', (ROOT / 'live_host.py').read_bytes())
        return {'instance_id': host['id'], 'receipts': json.loads(result.stdout)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        hosts = list(pool.map(observe, binding['hosts']))
    starts = []
    goals = []
    for host in hosts:
        receipts = host['receipts']
        starts.append(receipts['codex-process-start']['create_time'] + receipts['boot-clock-correction']['psutil_epoch_correction_seconds'])
        native = receipts['native-goals']['goals']
        assert len(native) == 1
        assert native[0]['objective'] == (ROOT / 'objective.txt').read_text().strip()
        goals.extend(native)
    report = {'observed_at': time.time(), 'subjects': len(hosts), 'accepted_goals': len(goals),
        'start_skew_seconds': max(starts) - min(starts), 'first_start_delta': min(starts) - release['T_start'],
        'last_start_delta': max(starts) - release['T_start'],
        'states': dict(collections.Counter(goal['status'] for goal in goals)), 'hosts': hosts}
    save(args.directory, f'live-receipts-{int(report["observed_at"])}.json', report)
    print(json.dumps({key: value for key, value in report.items() if key != 'hosts'}))


if __name__ == '__main__':
    main()
