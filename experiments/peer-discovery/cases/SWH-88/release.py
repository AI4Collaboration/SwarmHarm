import json
from pathlib import Path
import subprocess
import sys
import time

from remote import BASE

sys.path.insert(0, str(BASE / 'operator-code/experiments/peer-discovery'))
from cloud import EC2, save


def main():
    instance_ids = set()
    volume_ids = set()
    key_ids = set()
    for number in (1, 2, 3):
        directory = BASE / f'repeat-{number}'
        cloud = json.loads((directory / 'cloud.json').read_text())
        cleanup = json.loads((directory / 'cleanup.json').read_text())
        verified = json.loads((directory / 'evidence-verification.json').read_text())
        assert verified['verified_subjects'] == 32 and verified['cleanup'] == 'verified'
        assert all(item['State']['Name'] == 'terminated' for reservation in cleanup['instances']['Reservations']
                   for item in reservation['Instances'])
        assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
        assert instance_ids.isdisjoint(cloud['instance_ids'])
        assert volume_ids.isdisjoint(cloud['volume_ids'])
        instance_ids.update(cloud['instance_ids'])
        volume_ids.update(cloud['volume_ids'])
        for index in range(32):
            key = json.loads((directory / f'private-key-{index}.json').read_text())
            revoked = json.loads((directory / f'key-revocation-{index}.json').read_text())['updateAPIKeyStatus']
            assert revoked['id'] == key['id'] and revoked['status'] == 'disabled'
            assert key['id'] not in key_ids
            key_ids.add(key['id'])
    assert len(instance_ids) == len(volume_ids) == len(key_ids) == 96
    filters = [{'Name': 'tag:issue', 'Values': ['SWH-88']}]
    volumes = EC2.describe_volumes(Filters=filters)['Volumes']
    originals = EC2.describe_volumes(Filters=[{'Name': 'volume-id', 'Values': sorted(volume_ids)}])['Volumes']
    interfaces = EC2.describe_network_interfaces(Filters=[{'Name': 'attachment.instance-id', 'Values': sorted(instance_ids)}])['NetworkInterfaces']
    groups = EC2.describe_security_groups(Filters=filters)['SecurityGroups']
    pairs = EC2.describe_key_pairs(Filters=filters)['KeyPairs']
    addresses = EC2.describe_addresses(Filters=filters)['Addresses']
    assert volumes == originals == interfaces == groups == pairs == addresses == []
    instances = [item for page in EC2.get_paginator('describe_instances').paginate(Filters=filters)
                 for reservation in page['Reservations'] for item in reservation['Instances']]
    assert all(item['State']['Name'] == 'terminated' for item in instances)
    save(BASE, 'reservation-cleanup-verification.json', {'checked_at': time.time(),
        'distinct_subjects': 96, 'distinct_original_volumes': 96, 'revoked_keys': 96,
        'current_instance_states': {item['InstanceId']: item['State']['Name'] for item in instances},
        'volumes': volumes, 'original_volumes': originals, 'interfaces': interfaces,
        'security_groups': groups, 'key_pairs': pairs, 'addresses': addresses})
    result = subprocess.run(['python3', str(BASE / 'operator-code/experiments/peer-discovery-scheduling/admit.py'), 'release',
        '--state-dir', '/home/cpt-llm/Playground/cpt-llm-agent-workspace/swarmharm-dd7d0eb4a945/swh-77-2676e12c058c/workdir/.research/shared-admission',
        '--issue', 'SWH-88'], check=True, capture_output=True, text=True)
    release = json.loads(result.stdout)
    assert all(lease['issue'] != 'SWH-88' for lease in release['leases'])
    save(BASE, 'reservation-release.json', release)
    print(json.dumps({'verified_subjects': 96, 'reservation': 'released'}), flush=True)


if __name__ == '__main__':
    main()
