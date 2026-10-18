import argparse
import json
from pathlib import Path

from cloud import EC2, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    launch = json.loads((args.directory / 'launch-readback.json').read_text())
    original = [instance for reservation in launch['Reservations'] for instance in reservation['Instances']]
    interfaces = [interface['NetworkInterfaceId'] for instance in original for interface in instance['NetworkInterfaces']]
    instances = [instance for page in EC2.get_paginator('describe_instances').paginate(InstanceIds=cloud['instance_ids'])
                 for reservation in page['Reservations'] for instance in reservation['Instances']]
    volumes = [volume for page in EC2.get_paginator('describe_volumes').paginate(
        Filters=[{'Name': 'volume-id', 'Values': cloud['volume_ids']}]) for volume in page['Volumes']]
    remaining_interfaces = [interface for page in EC2.get_paginator('describe_network_interfaces').paginate(
        Filters=[{'Name': 'network-interface-id', 'Values': interfaces}]) for interface in page['NetworkInterfaces']]
    assert len(instances) == len(cloud['instance_ids'])
    assert all(instance['State']['Name'] == 'terminated' for instance in instances)
    assert volumes == [] and remaining_interfaces == []
    cleanup = json.loads((args.directory / 'cleanup.json').read_text())
    assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
    receipt = {'terminated_instances': cloud['instance_ids'], 'original_volume_ids': cloud['volume_ids'],
               'original_network_interface_ids': interfaces, 'remaining_volumes': volumes,
               'remaining_network_interfaces': remaining_interfaces, 'original_resource_cleanup': 'verified'}
    save(args.directory, 'cleanup-independent-verification.json', receipt)
    print(json.dumps({'instances': len(instances), 'deleted_original_volumes': len(cloud['volume_ids']),
                      'deleted_original_network_interfaces': len(interfaces)}))


if __name__ == '__main__':
    main()
