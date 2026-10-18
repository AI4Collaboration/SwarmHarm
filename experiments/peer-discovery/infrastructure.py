import argparse
import json
import time
from pathlib import Path

from cloud import EC2, save


def verify(directory):
    cloud = json.loads((directory / 'cloud.json').read_text())
    readback = EC2.describe_instances(InstanceIds=cloud['instance_ids'])
    volumes = EC2.describe_volumes(VolumeIds=cloud['volume_ids'])
    save(directory, 'infrastructure-instances.json', readback)
    save(directory, 'infrastructure-volumes.json', volumes)
    assert len(volumes['Volumes']) == len(cloud['instance_ids'])
    for volume in volumes['Volumes']:
        assert volume['Encrypted'] and volume['Size'] == 12 and volume['VolumeType'] == 'gp3'
    for reservation in readback['Reservations']:
        for instance in reservation['Instances']:
            assert instance['InstanceType'] == 't2.micro'
            assert instance['CpuOptions']['CoreCount'] * instance['CpuOptions']['ThreadsPerCore'] == 1
            assert instance['MetadataOptions']['HttpEndpoint'] == 'disabled'
            assert 'IamInstanceProfile' not in instance and instance['PublicIpAddress']
            assert all(mapping['Ebs']['DeleteOnTermination'] for mapping in instance['BlockDeviceMappings'])
    save(directory, 'infrastructure-verification.json', {'instances': len(cloud['instance_ids']),
        'vcpus_per_instance': 1, 'root_gib': 12, 'root_type': 'gp3', 'encrypted': True, 'delete_on_termination': True})
    return len(cloud['instance_ids'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--cleanup', action='store_true')
    args = parser.parse_args()
    if args.cleanup:
        cloud = json.loads((args.directory / 'cloud.json').read_text())
        launch = json.loads((args.directory / 'launch-readback.json').read_text())
        interfaces = [interface['NetworkInterfaceId'] for reservation in launch['Reservations']
                      for instance in reservation['Instances'] for interface in instance['NetworkInterfaces']]
        volumes = EC2.describe_volumes(Filters=[{'Name': 'volume-id', 'Values': cloud['volume_ids']}])['Volumes']
        remaining_interfaces = EC2.describe_network_interfaces(Filters=[{'Name': 'network-interface-id', 'Values': interfaces}])['NetworkInterfaces']
        assert not volumes and not remaining_interfaces
        save(args.directory, 'resource-deletion-verification.json', {'time': time.time(),
            'root_volume_ids': cloud['volume_ids'], 'network_interface_ids': interfaces,
            'remaining_volumes': volumes, 'remaining_interfaces': remaining_interfaces})
        print(json.dumps({'verified_deleted_root_volumes': len(cloud['volume_ids']), 'verified_deleted_interfaces': len(interfaces)}))
    else:
        print(json.dumps({'infrastructure_verified_subjects': verify(args.directory)}))


if __name__ == '__main__':
    main()
