import argparse
import datetime
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'repeats': []}
    for repeat in range(1, 4):
        directory = args.directory / f'repeat-{repeat}'
        if not directory.is_dir():
            continue
        row = {'repeat': repeat}
        for name, pattern in {
            'bootstrap': '*-bootstrap.txt', 'keys': 'private-key-*.json',
            'readiness': '*-readiness.json', 'connectivity': '*-connectivity.json',
            'timers': '*-timer.json', 'exports': 'host-export-receipts/*.json',
            'revocations': 'key-revocation-*.json',
        }.items():
            row[name] = len(list(directory.glob(pattern)))
        for name in ('release', 'cleanup', 'recording-independent-verification', 'evidence-verification',
                     'scoring-independent-verification', 'publication-independent-verification'):
            path = directory / f'{name}.json'
            row[name] = path.is_file()
        release = directory / 'release.json'
        if release.is_file():
            definition = json.loads(release.read_text())
            row['T_start'] = definition['T_start']
            row['seconds_to_deadline'] = round(definition['T_start'] + definition['allowance_seconds'] - time.time())
        observations = sorted((directory / 'observations').glob('snapshot-*.json'))
        for path in reversed(observations):
            observation = json.loads(path.read_text())
            if 'hosts' in observation:
                row['latest_hosts_observation'] = observation['time']
                row['invocations'] = sum(bool(host.get('markers')) for host in observation['hosts'])
                row['native_goals'] = sum(len(host.get('persisted_goals', [])) for host in observation['hosts'])
                row['outputs'] = sum(bool(host.get('output_exists')) for host in observation['hosts'])
                break
        result['repeats'].append(row)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
