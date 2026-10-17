import argparse
import concurrent.futures
import csv
import datetime
import hashlib
import io
import json
import shlex
import subprocess
import tarfile
import threading
import time
from pathlib import Path

import numpy as np

from cloud import EC2, ROOT, cleanup, launch, save, ssh
from graphs import validate
from preflight import put


def gateway(meta_key, mode, value):
    result = subprocess.run(['ssh', '-i', str(meta_key), '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
        'ubuntu@63.186.173.73', f'sudo python3 - {shlex.quote(mode)} {shlex.quote(value)}'],
        input=(ROOT / 'gateway.py').read_bytes(), capture_output=True, check=True)
    return json.loads(result.stdout)


def configure(directory, host, key, peer_key, objective):
    ip = host['public_ip']
    put(directory, ip, '/var/lib/peer-operator/inference-key', key['key'].encode())
    put(directory, ip, '/home/agent/.codex/config.toml', (ROOT / 'provider.toml').read_bytes(), owner='agent:agent')
    put(directory, ip, '/opt/peer-discovery/driver.py', (ROOT / 'driver.py').read_bytes(), mode='644')
    put(directory, ip, '/var/lib/peer-operator/objective.txt', objective)
    put(directory, ip, '/home/agent/peers.txt', ('\n'.join(host['seeds']) + '\n').encode(), owner='agent:agent')
    put(directory, ip, '/home/agent/.ssh/id_ed25519', peer_key.read_bytes(), owner='agent:agent')
    put(directory, ip, '/home/agent/.ssh/authorized_keys', peer_key.with_suffix('.pub').read_bytes(), owner='agent:agent')
    clock = ssh(directory, ip, 'chronyc -c tracking').stdout.decode().strip()
    fields = next(csv.reader([clock]))
    assert abs(float(fields[4])) <= 0.1 and fields[-1] == 'Normal', fields
    status = EC2.describe_instances(InstanceIds=[host['id']])['Reservations'][0]['Instances'][0]
    assert status['MetadataOptions']['HttpEndpoint'] == 'disabled'
    assert 'IamInstanceProfile' not in status
    readiness = ssh(directory, ip, 'sudo ufw status; sudo iptables -S; sudo ls -la /home/agent; sudo ls -la /home/agent/.ssh; sha256sum /home/agent/peers.txt /home/agent/.codex/config.toml; codex --version').stdout.decode()
    save(directory, f'{host["id"]}-readiness.json', {'clock_csv': clock, 'readiness': readiness, 'configuration': key['configuration']})
    ssh(directory, ip, 'sudo systemd-run --unit=peer-connectivity-probe --property=RuntimeMaxSec=60 /usr/bin/nc -lk -p 39271')


def arm(directory, host, timestamp, allowance):
    ip = host['public_ip']
    calendar = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    service = f'''[Unit]
Description=Peer discovery subject
[Service]
Type=exec
ExecStart=/usr/bin/python3 /opt/peer-discovery/driver.py {host['id']} /var/lib/peer-operator/objective.txt --deadline {timestamp + allowance}
Restart=no
KillMode=control-group
RuntimeMaxSec={allowance + 10}
'''
    timer = f'''[Unit]
Description=Peer discovery absolute release
[Timer]
OnCalendar={calendar}
AccuracySec=1ms
RandomizedDelaySec=0
Persistent=false
Unit=peer-subject.service
[Install]
WantedBy=timers.target
'''
    put(directory, ip, '/etc/systemd/system/peer-subject.service', service.encode(), mode='644')
    put(directory, ip, '/etc/systemd/system/peer-subject.timer', timer.encode(), mode='644')
    ssh(directory, ip, 'sudo systemctl daemon-reload && sudo systemctl start peer-subject.timer')
    readback = ssh(directory, ip, 'sudo systemctl show peer-subject.timer -p AccuracyUSec -p RandomizedDelayUSec -p NextElapseUSecRealtime -p TimersCalendar -p ActiveState; sudo systemctl show peer-subject.service -p Restart; chronyc -c tracking').stdout.decode()
    assert 'AccuracyUSec=1ms' in readback and 'RandomizedDelayUSec=0' in readback and 'Restart=no' in readback
    save(directory, f'{host["id"]}-timer.json', {'T_start': timestamp, 'calendar': calendar, 'readback': readback})
    ssh(directory, ip, 'sudo systemd-run --unit=peer-traffic --property=RuntimeMaxSec=1900 /usr/bin/tcpdump -i any -nn -s 128 -w /var/lib/peer-operator/traffic.pcap tcp')


def export_host(directory, host):
    ip = host['public_ip']
    ssh(directory, ip, 'sudo systemctl stop peer-subject.timer peer-subject.service peer-traffic.service')
    monitor = ssh(directory, ip, 'sudo journalctl -u peer-subject.service --no-pager; free -b; df -B1 /; ip -s link; chronyc tracking').stdout
    (directory / f'{host["id"]}-resource-end.txt').write_bytes(monitor)
    result = ssh(directory, ip, 'sudo tar -czf - --exclude=inference-key --exclude=packages --exclude=tmp --exclude=.tmp --exclude=skills --exclude=app-server-daemon -C / var/lib/peer-operator home/agent/.codex home/agent/peers.txt home/agent/discovered_peers.json', check=False)
    archive = directory / f'{host["id"]}-raw.tar.gz'
    archive.write_bytes(result.stdout)
    (directory / f'{host["id"]}-export-stderr.txt').write_bytes(result.stderr)
    with tarfile.open(archive) as bundle:
        bundle.extractall(directory / host['id'], filter='data')
    extracted = directory / host['id'] / 'var/lib/peer-operator'
    assert (extracted / 'process-stop.json').is_file()
    assert (extracted / 'native-goals.json').is_file()
    return {'instance_id': host['id'], 'archive_sha256': hashlib.sha256(result.stdout).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('graph', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--issue', default='SWH-78')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--existing-key', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    meta_key = args.meta_key.resolve()
    graph = json.loads(args.graph.read_text())
    assert validate(graph['adjacency'], graph['n'], graph['k'])[0]
    count = 1 if args.preflight else graph['n']
    purpose = 'preflight-2' if args.preflight else f'repeat-{graph["repeat"]}'
    lifetime = 3600 if args.preflight else 7200
    allowance = 300 if args.preflight else 1800
    keys = []
    directory.mkdir(parents=True, exist_ok=True)
    def expire():
        state = json.loads((directory / 'cloud.json').read_text())
        if state['instance_ids']:
            save(directory, 'external-lifetime-termination.json', EC2.terminate_instances(InstanceIds=state['instance_ids']))
    watchdog = threading.Timer(lifetime, expire)
    watchdog.start()
    try:
        if not (directory / 'cloud.json').exists():
            launch(directory, count, purpose, args.issue, graph['n'], graph['k'], lifetime)
        cloud = json.loads((directory / 'cloud.json').read_text())
        watchdog.cancel()
        watchdog = threading.Timer(max(0, cloud['created_at'] + lifetime - time.time()), expire)
        watchdog.start()
        hosts = cloud['hosts']
        rng = np.random.Generator(np.random.PCG64(graph['assignment_seed']))
        hosts = [hosts[int(index)] for index in rng.permutation(len(hosts))]
        ips = [host['public_ip'] for host in hosts]
        for index, host in enumerate(hosts):
            host['seeds'] = [] if args.preflight else [ips[j] for j in graph['adjacency'][index]]
            if args.existing_key:
                key = json.loads(args.existing_key.read_text())
            else:
                key = gateway(meta_key, 'create', f'{args.issue.lower()}-{purpose}-{index}')
            keys.append(key)
            save(directory, f'private-key-{index}.json', key)
        binding = {'repeat': graph['repeat'], 'hosts': hosts, 'graph_sha256': hashlib.sha256(args.graph.read_bytes()).hexdigest()}
        save(directory, 'binding.json', binding)
        peer_key = directory / 'peer-key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', '', '-f', str(peer_key)], check=True)
        objective = (ROOT / ('preflight-objective.txt' if args.preflight else 'objective.txt')).read_bytes()
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 16)) as pool:
            list(pool.map(lambda pair: configure(directory, pair[0], pair[1], peer_key, objective), zip(hosts, keys)))
            for host in hosts:
                for peer in hosts:
                    if host['id'] != peer['id']:
                        ssh(directory, host['public_ip'], f'nc -z -w 5 {peer["public_ip"]} 39271')
            list(pool.map(lambda host: ssh(directory, host['public_ip'], 'sudo systemctl stop peer-connectivity-probe.service'), hosts))
            timestamp = int(time.time()) + 125
            save(directory, 'release.json', {'T_start': timestamp, 'allowance_seconds': allowance, 'prepared_at': time.time()})
            list(pool.map(lambda host: arm(directory, host, timestamp, allowance), hosts))
            assert time.time() < timestamp - 20
            while time.time() < timestamp + allowance + 15:
                results = list(pool.map(lambda host: ssh(directory, host['public_ip'],
                    'sudo test -f /var/lib/peer-operator/process-stop.json', check=False), hosts))
                if all(result.returncode == 0 for result in results):
                    break
                time.sleep(5)
            receipts = list(pool.map(lambda host: export_host(directory, host), hosts))
        save(directory, 'export-manifest.json', receipts)
        for index, key in enumerate(keys):
            save(directory, f'gateway-{index}.json', gateway(meta_key, 'export', key['id']))
        print(json.dumps({'purpose': purpose, 'exports': len(receipts), 'T_start': timestamp}), flush=True)
    finally:
        try:
            for index, key in enumerate(keys):
                save(directory, f'key-revocation-{index}.json', gateway(meta_key, 'disable', key['id']))
        finally:
            try:
                cleanup(directory)
            finally:
                watchdog.cancel()
                watchdog.join()


if __name__ == '__main__':
    main()
