import argparse
import json
import time
from pathlib import Path

from cloud import EC2, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    launched = json.loads((args.directory / 'launch-readback.json').read_text())
    original_interfaces = sorted(interface['NetworkInterfaceId']
        for reservation in launched['Reservations'] for instance in reservation['Instances']
        for interface in instance['NetworkInterfaces'])
    assert len(original_interfaces) == len(set(original_interfaces)) == len(cloud['instance_ids'])
    instances = [instance for reservation in EC2.describe_instances(InstanceIds=cloud['instance_ids'])['Reservations']
                 for instance in reservation['Instances']]
    assert all(instance['State']['Name'] == 'terminated' for instance in instances)
    volumes = EC2.describe_volumes(Filters=[{'Name': 'volume-id', 'Values': cloud['volume_ids']}])['Volumes']
    interfaces = EC2.describe_network_interfaces(Filters=[
        {'Name': 'network-interface-id', 'Values': original_interfaces}])['NetworkInterfaces']
    groups = EC2.describe_security_groups(Filters=[{'Name': 'group-id', 'Values': [cloud['security_group_id']]}])['SecurityGroups']
    keys = EC2.describe_key_pairs(Filters=[{'Name': 'key-name', 'Values': [cloud['key_name']]}])['KeyPairs']
    addresses = EC2.describe_addresses(Filters=[{'Name': 'tag:issue', 'Values': [cloud['issue']]},
                                              {'Name': 'tag:purpose', 'Values': [cloud['purpose']]}])['Addresses']
    assert not volumes and not interfaces and not groups and not keys and not addresses
    result = {'time': time.time(), 'terminated_instance_ids': sorted(instance['InstanceId'] for instance in instances),
              'original_volume_ids': cloud['volume_ids'], 'original_interface_ids': original_interfaces,
              'remaining_volumes': volumes,
              'remaining_interfaces': interfaces, 'remaining_security_groups': groups,
              'remaining_ssh_key_pairs': keys, 'remaining_elastic_addresses': addresses}
    save(args.directory, 'independent-cleanup-verification.json', result)
    print(json.dumps({'terminated_instances': len(instances), 'original_root_volumes': len(cloud['volume_ids']),
                      'cloud_cleanup': 'verified'}))


if __name__ == '__main__':
    main()
