import argparse
import concurrent.futures
import json
from pathlib import Path

from cloud import save, ssh
from preflight import put


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    def extend(host):
        ssh(args.directory, host['public_ip'], 'sudo mkdir -p /run/systemd/system/peer-traffic.service.d')
        put(args.directory, host['public_ip'], '/run/systemd/system/peer-traffic.service.d/lifetime.conf', b'[Service]\nRuntimeMaxSec=3600\n', mode='644')
        response = ssh(args.directory, host['public_ip'],
            'sudo systemctl daemon-reload && sudo systemctl show peer-traffic.service -p RuntimeMaxUSec -p ActiveState')
        readback = response.stdout.decode()
        assert 'ActiveState=active' in readback and 'RuntimeMaxUSec=1h' in readback
        save(args.directory, f'{host["id"]}-capture-duration.json', {'instance_id': host['id'], 'readback': readback})
        return host['id']
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        print(json.dumps({'capture_duration_verified': list(pool.map(extend, binding['hosts']))}))


if __name__ == '__main__':
    main()
