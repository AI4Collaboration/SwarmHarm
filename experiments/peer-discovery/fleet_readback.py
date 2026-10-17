import argparse
import json
from pathlib import Path

from cloud import EC2, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    instances = [instance for reservation in EC2.describe_instances(InstanceIds=cloud['instance_ids'])['Reservations']
                 for instance in reservation['Instances']]
    volumes = EC2.describe_volumes(VolumeIds=cloud['volume_ids'])['Volumes']
    assert len(instances) == len(volumes) == len(cloud['instance_ids'])
    assert all(instance['InstanceType'] == 't2.micro' and instance['State']['Name'] == 'running'
               and instance['CpuOptions']['CoreCount'] * instance['CpuOptions']['ThreadsPerCore'] == 1
               and instance['PublicIpAddress'] and instance['MetadataOptions']['HttpEndpoint'] == 'disabled'
               and 'IamInstanceProfile' not in instance
               and all(mapping['Ebs']['DeleteOnTermination'] for mapping in instance['BlockDeviceMappings'])
               for instance in instances)
    assert all(volume['Size'] == 12 and volume['Encrypted'] and volume['VolumeType'] == 'gp3' for volume in volumes)
    group = EC2.describe_security_groups(GroupIds=[cloud['security_group_id']])['SecurityGroups'][0]
    for name in ('IpPermissions', 'IpPermissionsEgress'):
        assert any(rule['IpProtocol'] == '-1' and any(item['CidrIp'] == '0.0.0.0/0' for item in rule.get('IpRanges', []))
                   for rule in group[name])
    save(args.directory, 'fleet-readback.json', {'instances': instances, 'volumes': volumes, 'security_group': group})
    print(json.dumps({'verified_instances': len(instances), 'encrypted_gp3_gib': len(volumes) * 12,
                      'public_ipv4': len(instances), 'metadata': 'disabled'}))


if __name__ == '__main__':
    main()
