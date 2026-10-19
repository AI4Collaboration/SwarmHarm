import argparse
import csv
import hashlib
import json
from pathlib import Path

import jsonlines

from graphs import validate


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('graph', type=Path)
    args = parser.parse_args()
    directory = args.directory
    graph = read(args.graph)
    assert validate(graph['adjacency'], graph['n'], graph['k'])[0]
    binding = read(directory / 'binding.json')
    assert binding['graph_sha256'] == hashlib.sha256(args.graph.read_bytes()).hexdigest()
    hosts = binding['hosts']
    assert len(hosts) == graph['n']
    assert len({host['id'] for host in hosts}) == len(hosts)
    assert len({host['public_ip'] for host in hosts}) == len(hosts)
    manifests = {row['instance_id']: row for row in read(directory / 'export-manifest.json')}
    for index, host in enumerate(hosts):
        instance_id = host['id']
        root = directory / instance_id / 'var/lib/peer-operator'
        assert hashlib.sha256((directory / f'{instance_id}-raw.tar.gz').read_bytes()).hexdigest() == manifests[instance_id]['archive_sha256']
        expected = [hosts[target]['public_ip'] for target in graph['adjacency'][index]]
        actual = (directory / instance_id / 'home/agent/peers.txt').read_text().splitlines()
        assert expected == actual == host['seeds']
        goal = read(root / 'native-goals.json')['goals']
        assert len(goal) == 1
        assert goal[0]['objective'] == (root / 'objective.txt').read_text().strip()
        assert goal[0]['objective'] == Path(__file__).with_name('objective.txt').read_text().strip()
        sessions = list((directory / instance_id / 'home/agent/.codex/sessions').rglob('*.jsonl'))
        assert len(sessions) == 1
        with jsonlines.open(sessions[0]) as events:
            metadata = [event['payload'] for event in events if event['type'] == 'session_meta']
        assert len(metadata) == 1 and metadata[0]['id'] == goal[0]['thread_id']
        readiness = read(directory / f'{instance_id}-readiness.json')
        assert abs(float(next(csv.reader([readiness['clock_csv']]))[4])) <= 0.1
        assert 'codex-cli 0.160.0' in readiness['readiness']
        configuration = readiness['configuration']['updateAPIKeyProfiles']
        assert configuration['type'] == 'user'
        assert sorted(configuration['scopes']) == ['read_channels', 'write_requests']
        profiles = configuration['profiles']['profiles']
        assert len(profiles) == 1 and profiles[0]['modelIDs'] == ['gpt-6.1-sol']
        assert profiles[0]['quota']['requests'] == 100 and profiles[0]['quota']['totalTokens'] == 200000
        guard = read(directory / f'{instance_id}-invocation-guard.json')
        assert guard['receipt_unchanged'] and guard['duplicate_returncode'] != 0
        receipt = read(root / 'collection-receipt.json')
        assert receipt['launch_markers'] == [instance_id]
        assert hashlib.sha256((root / 'executed-driver.py').read_bytes()).hexdigest() == receipt['files']['/opt/peer-discovery/driver.py']['sha256']
        revoked = read(directory / f'key-revocation-{index}.json')['updateAPIKeyStatus']
        assert revoked['status'] == 'disabled'
        assert revoked['id'] == configuration['id'] == read(directory / f'private-key-{index}.json')['id']
    cleanup = read(directory / 'cleanup.json')
    terminated = [instance['InstanceId'] for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances'] if instance['State']['Name'] == 'terminated']
    assert set(terminated) == {host['id'] for host in hosts}
    assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
    result = {'repeat': binding['repeat'], 'verified_subjects': len(hosts), 'graph_sha256': binding['graph_sha256'],
        'exports': 'verified', 'sessions_per_subject': 1, 'native_goal_objectives': 'verified', 'cleanup': 'verified', 'scoped_keys': 'disabled'}
    (directory / 'evidence-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
