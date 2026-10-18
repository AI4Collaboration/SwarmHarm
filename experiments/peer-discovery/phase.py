import argparse
import json
from pathlib import Path

from cloud import ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--inspect-bootstrap', action='store_true')
    args = parser.parse_args()
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    result = {'instances': len(cloud['instance_ids'])}
    for name, pattern in [('bootstrap', '*-bootstrap.txt'), ('keys', 'private-key-*.json'),
                          ('readiness', '*-readiness.json'), ('timers', '*-timer.json'),
                          ('exports', '*-raw.tar.gz'), ('key_revocations', 'key-revocation-*.json')]:
        result[name] = len(list(args.directory.glob(pattern)))
    release = args.directory / 'release.json'
    if release.exists():
        result['release'] = json.loads(release.read_text())
    result['cleanup'] = (args.directory / 'cleanup.json').exists()
    print(json.dumps(result))
    if args.inspect_bootstrap:
        pending = [host for host in cloud.get('hosts', [])
                   if not (args.directory / f'{host["id"]}-bootstrap.txt').exists()]
        if pending:
            host = pending[0]
            print(host['id'])
            print(ssh(args.directory, host['public_ip'],
                "ps -eo pid,ppid,etime,args | rg 'apt|dpkg|curl|chrony|codex|bash'", check=False).stdout.decode())


if __name__ == '__main__':
    main()
