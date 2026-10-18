import concurrent.futures
import json
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'operator-code/experiments/peer-discovery'))
from cloud import save, ssh


def main():
    number = int(sys.argv[1])
    directory = BASE / f'repeat-{number}'
    cloud = json.loads((directory / 'cloud.json').read_text())
    row = {'repeat': number, 'observed_at': time.time(), 'instances': len(cloud['instance_ids']),
           'bootstrap_receipts': len(list(directory.glob('*-bootstrap.txt'))),
           'readiness_receipts': len(list(directory.glob('*-readiness.json'))),
           'timer_receipts': len(list(directory.glob('*-timer.json')))}
    release = directory / 'release.json'
    if release.exists():
        row['release'] = json.loads(release.read_text())
    if '--hosts' in sys.argv:
        hosts = [host for host in cloud['hosts'] if not (directory / f"{host['id']}-bootstrap.txt").exists()]

        def inspect(host):
            result = ssh(directory, host['public_ip'], 'ps -eo pid,ppid,etime,comm,args; free -m; systemctl list-jobs --no-pager', check=False)
            return {'instance_id': host['id'], 'returncode': result.returncode, 'state': result.stdout.decode()}

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            save(directory, f'bootstrap-observation-{time.time_ns()}.json', list(pool.map(inspect, hosts)))
    print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
