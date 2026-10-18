import argparse
import bisect
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
import tarfile
from pathlib import Path

from packets import tcp_records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory
    binding = json.loads((directory / 'binding.json').read_text())
    release = json.loads((directory / 'release.json').read_text())
    issue = json.loads((directory / 'cloud.json').read_text())['issue']
    start = release['T_start']
    deadline = start + release['allowance_seconds']
    own = {host[address]: host for host in binding['hosts'] for address in ('private_ip', 'public_ip')}
    snapshots = sorted((json.loads(path.read_text()) for path in directory.glob('context-*.json')),
                       key=lambda record: record['time'])
    assert snapshots
    times = [snapshot['time'] for snapshot in snapshots]
    maps = [{instance[address]: instance for instance in snapshot['instances']
             for address in ('private_ip', 'public_ip')} for snapshot in snapshots]
    public = {}
    for snapshot in snapshots:
        for instance in snapshot['instances']:
            public.setdefault(instance['public_ip'], {})[instance['instance_id']] = instance
    rows = {}
    within_contacts = set()
    within_syn = set()
    capture_hashes = {}
    for host in binding['hosts']:
        member = 'var/lib/peer-operator/traffic.pcap'
        extracted = directory / host['id'] / member
        with ExitStack() as stack:
            if extracted.exists():
                stream = stack.enter_context(extracted.open('rb'))
            else:
                archive = stack.enter_context(tarfile.open(directory / f'{host["id"]}-raw.tar.gz'))
                stream = stack.enter_context(archive.extractfile(member))
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            capture_hashes[host['id']] = digest
            stream.seek(0)
            for timestamp, source, destination, length, flags, sport, dport in tcp_records(stream):
                if source is None or timestamp < start:
                    continue
                if source in (host['private_ip'], host['public_ip']):
                    direction, remote, remote_port, local_port = 'outbound', destination, dport, sport
                elif destination in (host['private_ip'], host['public_ip']):
                    direction, remote, remote_port, local_port = 'inbound', source, sport, dport
                else:
                    continue
                window = 'timed_window' if timestamp <= deadline else 'collection'
                initial_syn = bool(flags & 2 and not flags & 16)
                if remote in own:
                    peer = own[remote]
                    if window == 'timed_window' and direction == 'outbound' and peer['id'] != host['id']:
                        within_contacts.add((host['id'], peer['id']))
                        if initial_syn:
                            within_syn.add((host['id'], peer['id']))
                    continue
                index = max(0, bisect.bisect_right(times, timestamp) - 1)
                instance = maps[index].get(remote)
                basis = f'snapshot:{times[index]}'
                if remote in public and len(public[remote]) == 1:
                    instance = next(iter(public[remote].values()))
                    basis = 'public_address_in_context'
                if instance is None or instance['tags']['issue'] == issue:
                    continue
                key = (host['id'], window, direction, remote, remote_port, local_port,
                       instance['instance_id'], basis)
                if key not in rows:
                    rows[key] = {'instance_id': host['id'], 'window': window, 'direction': direction,
                        'remote_raw_ip': remote, 'remote_public_ip': instance['public_ip'],
                        'remote_port': remote_port, 'local_port': local_port,
                        'context_instance_id': instance['instance_id'], 'context_issue': instance['tags']['issue'],
                        'attribution_basis': basis, 'first_packet': timestamp, 'last_packet': timestamp,
                        'packets': 0, 'bytes': 0, 'initial_syn_packets': 0, 'tcp_flags': Counter()}
                row = rows[key]
                row['packets'] += 1
                row['bytes'] += length
                row['initial_syn_packets'] += initial_syn
                row['last_packet'] = timestamp
                row['tcp_flags'][str(flags)] += 1
    totals = {}
    for window in ('timed_window', 'collection'):
        for direction in ('outbound', 'inbound'):
            selected = [row for row in rows.values() if row['window'] == window and row['direction'] == direction]
            totals[f'{window}_{direction}'] = {
                'subjects': len({row['instance_id'] for row in selected}),
                'context_cases': sorted({row['context_issue'] for row in selected}),
                'packets': sum(row['packets'] for row in selected),
                'initial_syn_packets': sum(row['initial_syn_packets'] for row in selected)}
    report = {'repeat': binding['repeat'], 'T_start': start, 'deadline': deadline,
        'attribution': 'Public addresses use captured context identity; private addresses use the latest preceding snapshot, with the earliest snapshot covering the release interval. Snapshot times bound identity evidence during address reuse.',
        'timed_window_directed_peer_packet_pairs': len(within_contacts),
        'timed_window_directed_peer_syn_pairs': len(within_syn),
        'cross_case_totals': totals, 'cross_case_records': list(rows.values()),
        'capture_sha256': capture_hashes,
        'context_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in directory.glob('context-*.json')}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('cross_case_records', 'capture_sha256', 'context_sha256')}))


if __name__ == '__main__':
    main()
