import argparse
import json
import time
from pathlib import Path

from cloud import EC2, save


def snapshot(directory):
    hosts = []
    for page in EC2.get_paginator('describe_instances').paginate(Filters=[{'Name': 'tag:parent', 'Values': ['SWH-77']}]):
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:
                tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                hosts.append({'instance_id': instance['InstanceId'], 'state': instance['State']['Name'],
                    'public_ip': instance.get('PublicIpAddress'), 'private_ip': instance.get('PrivateIpAddress'),
                    'issue': tags.get('issue'), 'purpose': tags.get('purpose'), 'case': tags.get('case')})
    report = {'time': time.time(), 'hosts': hosts}
    save(directory, f'simultaneous-inventory-{int(report["time"])}.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    report = snapshot(args.directory)
    print(json.dumps({'observed_instances': len(report['hosts']),
        'active_cases': sorted({host['issue'] for host in report['hosts'] if host['state'] in ('pending', 'running')})}))


if __name__ == '__main__':
    main()
