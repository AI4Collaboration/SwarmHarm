import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path

from cloud import ROOT, ssh


def put(directory, host, destination, contents, mode='600', owner='root:root'):
    command = f'sudo install -o {owner.split(":")[0]} -g {owner.split(":")[1]} -m {mode} /dev/stdin {shlex.quote(destination)}'
    return ssh(directory, host, command, contents)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('key_file', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    cloud = json.loads((directory / 'cloud.json').read_text())
    host = cloud['hosts'][0]
    key = json.loads(args.key_file.read_text())
    put(directory, host['public_ip'], '/var/lib/peer-operator/inference-key', key['key'].encode())
    put(directory, host['public_ip'], '/home/agent/.codex/config.toml', (ROOT / 'provider.toml').read_bytes(), owner='agent:agent')
    put(directory, host['public_ip'], '/opt/peer-discovery/driver.py', (ROOT / 'driver.py').read_bytes(), mode='644')
    put(directory, host['public_ip'], '/var/lib/peer-operator/objective.txt', (ROOT / 'preflight-objective.txt').read_bytes())
    result = ssh(directory, host['public_ip'], '/usr/local/bin/codex --version; /usr/local/bin/codex --help')
    (directory / 'codex-help.txt').write_bytes(result.stdout)
    deadline = int(time.time()) + 300
    command = f'sudo python3 /opt/peer-discovery/driver.py {host["id"]} /var/lib/peer-operator/objective.txt --deadline {deadline}'
    result = ssh(directory, host['public_ip'], command, check=False)
    (directory / 'driver-console.txt').write_bytes(result.stdout + result.stderr)
    print(json.dumps({'driver_returncode': result.returncode, 'instance': host['id']}))
    export = ssh(directory, host['public_ip'], 'sudo tar -czf - --exclude=inference-key --exclude=packages --exclude=tmp --exclude=.tmp --exclude=skills --exclude=app-server-daemon -C / var/lib/peer-operator home/agent/.codex home/agent/shell-admission.txt home/agent/discovered_peers.json', check=False)
    (directory / 'evidence.tar.gz').write_bytes(export.stdout)
    (directory / 'export-stderr.txt').write_bytes(export.stderr)
    view = ssh(directory, host['public_ip'], 'sudo cat /var/lib/peer-operator/pty.txt /var/lib/peer-operator/process-stop.json', check=False)
    (directory / 'admission-view.txt').write_bytes(view.stdout)
    print(view.stdout.decode()[-12000:])
    assert result.returncode == 0


if __name__ == '__main__':
    main()
