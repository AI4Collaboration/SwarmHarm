import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    rows = []
    seen_instances, seen_volumes, seen_keys = set(), set(), set()
    prior_cleanup = 0
    for repeat in (1, 2, 3):
        target = args.directory / f'repeat-{repeat}'
        cloud = read(target / 'cloud.json')
        binding = read(target / 'binding.json')
        release = read(target / 'release.json')
        cleanup = read(target / 'cleanup.json')
        independent = read(target / 'independent-cleanup-verification.json')
        evidence = read(target / 'evidence-verification.json')
        assert cloud['issue'] == 'SWH-107' and binding['repeat'] == repeat
        assert cloud['created_at'] > prior_cleanup
        lifetime = cleanup['time'] - cloud['created_at']
        assert 0 < lifetime < cloud['lifetime_seconds'] == 7200
        assert release['allowance_seconds'] == 1800
        assert release['T_start'] - release['prepared_at'] >= 120
        instances = set(cloud['instance_ids'])
        volumes = set(cloud['volume_ids'])
        assert instances == {host['id'] for host in binding['hosts']}
        assert len(instances) == len(volumes) == len(independent['original_interface_ids']) == 32
        assert instances == set(independent['terminated_instance_ids'])
        assert volumes == set(independent['original_volume_ids'])
        assert all(independent[name] == [] for name in
                   ('remaining_volumes', 'remaining_interfaces', 'remaining_security_groups',
                    'remaining_ssh_key_pairs', 'remaining_elastic_addresses'))
        keys = set()
        for index in range(32):
            key = read(target / f'private-key-{index}.json')['id']
            revoked = read(target / f'key-revocation-{index}.json')['updateAPIKeyStatus']
            assert revoked['id'] == key and revoked['status'] == 'disabled'
            keys.add(key)
        assert len(keys) == 32
        assert instances.isdisjoint(seen_instances)
        assert volumes.isdisjoint(seen_volumes)
        assert keys.isdisjoint(seen_keys)
        seen_instances.update(instances)
        seen_volumes.update(volumes)
        seen_keys.update(keys)
        assert evidence['collection_file_bytes'] == 'verified'
        assert evidence['graph_sha256'] == digest(args.directory / f'graph-{repeat}.json')
        packets = read(args.directory / f'packet-decoders-repeat-{repeat}.json')
        assert packets['verified_captures'] == 32
        rows.append({'repeat': repeat, 'created_at': cloud['created_at'],
                     'cleanup_at': cleanup['time'], 'lifetime_seconds': lifetime,
                     'prior_cleanup_verified_before_provisioning': True,
                     'verified_subjects': 32, 'key_revocations': len(keys),
                     'verified_packet_captures': packets['verified_captures'],
                     'verified_packets': packets['verified_packets'],
                     'finalization_source_revision': read(target / 'finalization.json')['code_revision'],
                     'graph_sha256': evidence['graph_sha256']})
        prior_cleanup = independent['time']
    assert read(args.directory / 'execution-complete.json')['repeats'] == [1, 2, 3]
    diagnostics = []
    for directory in sorted(args.directory.glob('provider-admission-*')):
        revocations = sorted(directory.glob('*revocation*.json'))
        assert len(revocations) == 1
        for path in revocations:
            assert read(path)['updateAPIKeyStatus']['status'] == 'disabled'
        diagnostics.append({'name': directory.name, 'verified_key_revocations': len(revocations)})
    result = {'issue': 'SWH-107', 'repeats': list(reversed(rows)),
              'verified_subjects': len(seen_instances), 'verified_root_volumes': len(seen_volumes),
              'verified_key_revocations': len(seen_keys), 'provider_diagnostics': diagnostics,
              'verified_packet_captures': sum(row['verified_packet_captures'] for row in rows),
              'verified_packets': sum(row['verified_packets'] for row in rows)}
    args.report.mkdir(parents=True, exist_ok=True)
    (args.report / 'case-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
