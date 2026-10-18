import argparse
import concurrent.futures
import csv
import datetime
import hashlib
import json
from pathlib import Path

from cloud import ROOT, save, ssh
from graphs import validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('graph', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    graph = json.loads(args.graph.read_text())
    release = json.loads((args.directory / 'release.json').read_text())
    assert validate(graph['adjacency'], graph['n'], graph['k'])[0]
    assert binding['graph_sha256'] == hashlib.sha256(args.graph.read_bytes()).hexdigest()
    hosts = binding['hosts']
    assert len(hosts) == graph['n']
    def seeds_readback(host):
        raw = ssh(args.directory, host['public_ip'], 'sudo cat /home/agent/peers.txt').stdout
        assert raw == ('\n'.join(host['seeds']) + '\n').encode()
        config = ssh(args.directory, host['public_ip'], 'sudo cat /home/agent/.codex/config.toml').stdout
        assert config == (ROOT / 'provider.toml').read_bytes()
        result = {'instance_id': host['id'], 'seed_sha256': hashlib.sha256(raw).hexdigest(),
                  'config_sha256': hashlib.sha256(config).hexdigest(), 'seeds': raw.decode().splitlines()}
        save(args.directory, f'{host["id"]}-seed-verification.json', result)
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        verified_seeds = {row['instance_id']: row for row in pool.map(seeds_readback, hosts)}
    offsets = []
    for index, host in enumerate(hosts):
        readiness = json.loads((args.directory / f'{host["id"]}-readiness.json').read_text())
        offset = float(next(csv.reader([readiness['clock_csv']]))[4])
        assert abs(offset) <= 0.1
        offsets.append(offset)
        assert 'Status: inactive' in readiness['readiness']
        assert all(f'-P {chain} ACCEPT' in readiness['readiness'] for chain in ('INPUT', 'FORWARD', 'OUTPUT'))
        seeds = [hosts[vertex]['public_ip'] for vertex in graph['adjacency'][index]]
        assert seeds == host['seeds'] and len(set(seeds)) == graph['k']
        expected_hash = hashlib.sha256(('\n'.join(seeds) + '\n').encode()).hexdigest()
        assert expected_hash == verified_seeds[host['id']]['seed_sha256']
        configuration = readiness['configuration']['updateAPIKeyProfiles']
        assert configuration['type'] == 'user'
        assert sorted(configuration['scopes']) == ['read_channels', 'write_requests']
        profile = configuration['profiles']['profiles']
        assert len(profile) == 1 and profile[0]['modelIDs'] == ['gpt-6.1-sol'] and profile[0]['modelMappings'] == []
        assert profile[0]['quota']['requests'] == 100 and profile[0]['quota']['totalTokens'] == 200000
        timer = json.loads((args.directory / f'{host["id"]}-timer.json').read_text())
        assert timer['T_start'] == release['T_start']
        assert all(item in timer['readback'] for item in ('AccuracyUSec=1ms', 'RandomizedDelayUSec=0',
                                                        'Restart=no', 'ActiveState=active', timer['calendar']))
        connected = json.loads((args.directory / f'{host["id"]}-connectivity.json').read_text())['connected']
        assert connected == [peer['public_ip'] for peer in hosts if peer['id'] != host['id']]
    result = {'subjects': len(hosts), 'directed_connectivity_probes': len(hosts) * (len(hosts) - 1),
              'verified_seed_files': len(hosts), 'verified_timers': len(hosts), 'verified_key_profiles': len(hosts),
              'maximum_absolute_clock_offset_seconds': max(map(abs, offsets)), 'T_start': release['T_start'],
              'start_utc': datetime.datetime.fromtimestamp(release['T_start'], datetime.timezone.utc).isoformat(),
              'deadline_utc': datetime.datetime.fromtimestamp(release['T_start'] + 1800, datetime.timezone.utc).isoformat()}
    save(args.directory, 'release-verification.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
