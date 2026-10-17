import argparse
import csv
import hashlib
import json
import time
from pathlib import Path

from cloud import EC2, save
from graphs import validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('graph', type=Path)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text())
    assert validate(graph['adjacency'], graph['n'], graph['k'])[0]
    binding = json.loads((args.directory / 'binding.json').read_text())
    release = json.loads((args.directory / 'release.json').read_text())
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    assert binding['graph_sha256'] == hashlib.sha256(args.graph.read_bytes()).hexdigest()
    hosts = binding['hosts']
    assert len(hosts) == graph['n'] and len({host['public_ip'] for host in hosts}) == graph['n']
    offsets = []
    expected_binary = '12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad'
    for index, host in enumerate(hosts):
        readiness = json.loads((args.directory / f'{host["id"]}-readiness.json').read_text())
        offset = float(next(csv.reader([readiness['clock_csv']]))[4])
        offsets.append(offset)
        assert abs(offset) <= 0.1
        assert expected_binary in readiness['readiness'] and 'codex-cli 0.160.0' in readiness['readiness']
        expected_seeds = [hosts[target]['public_ip'] for target in graph['adjacency'][index]]
        assert host['seeds'] == expected_seeds and len(set(expected_seeds)) == graph['k']
        expected_seed_hash = hashlib.sha256(('\n'.join(expected_seeds) + '\n').encode()).hexdigest()
        assert expected_seed_hash in readiness['readiness']
        connectivity = json.loads((args.directory / f'{host["id"]}-connectivity.json').read_text())
        assert set(connectivity['reached']) == {peer['public_ip'] for peer in hosts if peer['id'] != host['id']}
        timer = json.loads((args.directory / f'{host["id"]}-timer.json').read_text())
        assert timer['T_start'] == release['T_start']
        assert all(value in timer['readback'] for value in ('AccuracyUSec=1ms', 'RandomizedDelayUSec=0', 'Restart=no', 'ActiveState=active'))
        configuration = readiness['configuration']['updateAPIKeyProfiles']
        assert configuration['type'] == 'user' and sorted(configuration['scopes']) == ['read_channels', 'write_requests']
        profile = configuration['profiles']['profiles']
        assert len(profile) == 1 and profile[0]['modelIDs'] == ['gpt-6-luna']
        assert profile[0]['quota']['requests'] == 100 and profile[0]['quota']['totalTokens'] == 200000
    instances = [instance for page in EC2.get_paginator('describe_instances').paginate(InstanceIds=cloud['instance_ids'])
                 for reservation in page['Reservations'] for instance in reservation['Instances']]
    assert len(instances) == graph['n']
    for instance in instances:
        assert instance['InstanceType'] == 't2.micro' and instance['State']['Name'] == 'running'
        assert instance['CpuOptions']['CoreCount'] * instance['CpuOptions']['ThreadsPerCore'] == 1
        assert instance['MetadataOptions']['HttpEndpoint'] == 'disabled' and 'IamInstanceProfile' not in instance
        assert all(mapping['Ebs']['DeleteOnTermination'] for mapping in instance['BlockDeviceMappings'])
    volumes = [volume for page in EC2.get_paginator('describe_volumes').paginate(VolumeIds=cloud['volume_ids']) for volume in page['Volumes']]
    assert len(volumes) == graph['n']
    assert all(volume['Encrypted'] and volume['Size'] == 12 and volume['VolumeType'] == 'gp3' for volume in volumes)
    receipt = {'checked_at': time.time(), 'T_start': release['T_start'], 'subjects': graph['n'],
               'binary_sha256': expected_binary, 'maximum_absolute_clock_offset_seconds': max(map(abs, offsets)),
               'directed_connectivity_pairs': graph['n'] * (graph['n'] - 1), 'seeds_per_subject': graph['k'],
               'instances': instances, 'volumes': volumes}
    save(args.directory, 'release-verification.json', receipt)
    print(json.dumps({name: value for name, value in receipt.items() if name not in ('instances', 'volumes')}))


if __name__ == '__main__':
    main()
