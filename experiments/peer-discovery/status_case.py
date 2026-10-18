import argparse
import datetime
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'storage_free_gib': round(shutil.disk_usage(args.directory).free / 2**30, 2),
              'repeats': []}
    for repeat in (1, 2, 3):
        directory = args.directory / f'repeat-{repeat}'
        cloud_path = directory / 'cloud.json'
        if not cloud_path.exists():
            continue
        cloud = json.loads(cloud_path.read_text())
        row = {'repeat': repeat, 'provisioned': len(cloud['instance_ids'])}
        for name, pattern in [('bootstrapped', '*-bootstrap.txt'), ('scoped_keys', 'private-key-*.json'),
                              ('ready', '*-readiness.json'), ('timers', '*-timer.json'),
                              ('exports', '*-raw.tar.gz')]:
            row[name] = len(list(directory.glob(pattern)))
        for name in ('release', 'launch-verification', 'cleanup', 'finalization'):
            path = directory / f'{name}.json'
            if path.exists():
                data = json.loads(path.read_text())
                row[name] = ({key: value for key, value in data.items() if key != 'rows'}
                             if name in ('release', 'launch-verification') else 'recorded')
        result['repeats'].append(row)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
