import argparse
import json
import subprocess
import time
from pathlib import Path

from cloud import EC2, save
from recording import policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--stage', required=True)
    args = parser.parse_args()
    instances = [instance for page in EC2.get_paginator('describe_instances').paginate(
        Filters=[{'Name': 'tag:parent', 'Values': ['SWH-77']},
                 {'Name': 'instance-state-name', 'Values': ['pending', 'running']}])
        for reservation in page['Reservations'] for instance in reservation['Instances']]
    inventory = [{'instance_id': instance['InstanceId'], 'public_ip': instance.get('PublicIpAddress'),
                  'private_ip': instance.get('PrivateIpAddress'),
                  'tags': {tag['Key']: tag['Value'] for tag in instance['Tags']}} for instance in instances]
    resources = subprocess.run(['ssh', '-i', str(args.meta_key), '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=15', 'ubuntu@63.186.173.73',
        'date -u; uptime; free -b; df -B1 /; ip -s link; sudo docker stats --no-stream --format "{{json .}}"'],
        check=True, capture_output=True, text=True)
    result = {'time': time.time(), 'stage': args.stage, 'instances': inventory,
              'gateway_resources': resources.stdout, 'gateway_policy_and_channels': policy(args.meta_key)}
    save(args.directory, f'context-{args.stage}.json', result)
    print(json.dumps({'stage': args.stage, 'active_subject_instances': len(inventory),
                      'cases': sorted({row['tags']['issue'] for row in inventory})}))


if __name__ == '__main__':
    main()
