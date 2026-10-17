import argparse
import collections
import concurrent.futures
import json
import subprocess
import time
from pathlib import Path

from cloud import EC2, ROOT, save, ssh
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--hosts', action='store_true')
    args = parser.parse_args()
    instances = [instance for page in EC2.get_paginator('describe_instances').paginate(
        Filters=[{'Name': 'tag:parent', 'Values': ['SWH-77']},
                 {'Name': 'instance-state-name', 'Values': ['pending', 'running']}])
        for reservation in page['Reservations'] for instance in reservation['Instances']]
    cases = collections.Counter(next(tag['Value'] for tag in instance['Tags'] if tag['Key'] == 'issue')
                                for instance in instances)
    result = {'time': time.time(), 'simultaneous_case_subjects': dict(cases),
              'simultaneous_instances': [{'id': instance['InstanceId'], 'public_ip': instance.get('PublicIpAddress'),
                  'private_ip': instance['PrivateIpAddress'],
                  'issue': next(tag['Value'] for tag in instance['Tags'] if tag['Key'] == 'issue')}
                  for instance in instances],
              'gateway': gateway(args.meta_key, 'recording', '')}
    hardware = subprocess.run(['ssh', '-i', str(args.meta_key), '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
        'ubuntu@63.186.173.73', 'date -u; uptime; free -b; df -B1 /; sudo docker stats --no-stream --format "{{json .}}"'],
        capture_output=True, check=True, text=True)
    result['gateway_hardware'] = hardware.stdout
    if args.hosts:
        cloud = json.loads((args.directory / 'cloud.json').read_text())
        def inspect(host):
            response = ssh(args.directory, host['public_ip'], 'sudo python3 -', (ROOT / 'host_status.py').read_bytes())
            return {'instance_id': host['id'], **json.loads(response.stdout)}
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            result['hosts'] = list(pool.map(inspect, cloud['hosts']))
    filename = f'observations/snapshot-{time.time_ns()}.json'
    (args.directory / 'observations').mkdir(exist_ok=True)
    save(args.directory, filename, result)
    print(json.dumps({'snapshot': filename, 'simultaneous_case_subjects': dict(cases),
        'markers': sum(bool(host['markers']) for host in result.get('hosts', [])),
        'goal_states': dict(collections.Counter(goal['status'] for host in result.get('hosts', [])
                                              for goal in host.get('persisted_goals', []))),
        'output_files': sum('discovered_peers.json' in host for host in result.get('hosts', []))}))


if __name__ == '__main__':
    main()
