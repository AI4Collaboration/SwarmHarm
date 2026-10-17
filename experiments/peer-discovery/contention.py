import argparse
import json
from pathlib import Path
import subprocess
import time

from cloud import EC2, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    args = parser.parse_args()
    stamp = time.time_ns()
    fleet = []
    pages = EC2.get_paginator('describe_instances').paginate(Filters=[
        {'Name': 'tag:parent', 'Values': ['SWH-77']},
        {'Name': 'instance-state-name', 'Values': ['pending', 'running']}])
    for page in pages:
        for reservation in page['Reservations']:
            for host in reservation['Instances']:
                tags = {item['Key']: item['Value'] for item in host['Tags']}
                fleet.append({'instance_id': host['InstanceId'], 'public_ip': host.get('PublicIpAddress'),
                    'private_ip': host['PrivateIpAddress'], 'issue': tags['issue'], 'purpose': tags['purpose']})
    stats = subprocess.run(['ssh', '-i', str(args.meta_key), '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=15', 'ubuntu@63.186.173.73',
        "date -u +%s; free -b; df -B1 /; sudo docker stats --no-stream --format '{{json .}}'"],
        check=True, capture_output=True, text=True)
    directory = args.directory / 'contention'
    save(directory, f'{stamp}.json', {'time_ns': stamp, 'fleet': fleet, 'gateway_resources': stats.stdout})
    print(json.dumps({'observed_at_ns': stamp, 'active_instances': len(fleet),
                      'simultaneous_cases': sorted({host['issue'] for host in fleet})}))


if __name__ == '__main__':
    main()
