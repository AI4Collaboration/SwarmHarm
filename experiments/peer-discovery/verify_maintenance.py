import argparse
import concurrent.futures
import json
from pathlib import Path

from cloud import save, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    hosts = json.loads((args.directory / 'cloud.json').read_text())['hosts']

    def inspect(host):
        response = ssh(args.directory, host['public_ip'],
                       'systemctl show apt-daily.timer apt-daily-upgrade.timer -p LoadState --value')
        states = response.stdout.decode().split()
        assert states == ['masked', 'masked'], (host['id'], states)
        return {'instance_id': host['id'], 'maintenance_timer_load_states': states}

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, hosts))
    save(args.directory, 'maintenance-verification.json', {'subjects': len(rows), 'hosts': rows})
    print(json.dumps({'subjects': len(rows), 'masked_maintenance_timers': len(rows) * 2}))


if __name__ == '__main__':
    main()
