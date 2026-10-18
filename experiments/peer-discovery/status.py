import argparse
import collections
import concurrent.futures
import json
from pathlib import Path

from cloud import ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--host-detail', action='store_true')
    args = parser.parse_args()
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    result = {'instances': len(cloud['instance_ids']), 'bootstrap_receipts': len(list(args.directory.glob('*-bootstrap.txt'))),
              'readiness_receipts': len(list(args.directory.glob('*-readiness.json'))),
              'timer_receipts': len(list(args.directory.glob('*-timer.json')))}
    release = args.directory / 'release.json'
    if release.exists():
        result['release'] = json.loads(release.read_text())
    if args.host_detail:
        def observe(host):
            command = 'sudo cat /var/lib/peer-operator/native-goals.json; sudo test -f /var/lib/peer-operator/process-stop.json'
            observation = ssh(args.directory, host['public_ip'], command, check=False)
            return {'instance_id': host['id'], 'ended': observation.returncode == 0,
                    'goals': json.loads(observation.stdout)['goals'] if observation.stdout else []}
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            observations = list(pool.map(observe, cloud['hosts']))
        result['states'] = dict(collections.Counter(goal['status'] for row in observations for goal in row['goals']))
        result['ended'] = sum(row['ended'] for row in observations)
        result['accepted_goals'] = sum(len(row['goals']) for row in observations)
        result['native_tokens_used'] = sum(goal['tokens_used'] for row in observations for goal in row['goals'])
    print(json.dumps(result))


if __name__ == '__main__':
    main()
