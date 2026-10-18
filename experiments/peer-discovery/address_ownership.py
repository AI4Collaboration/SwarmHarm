import collections
import json


def bindings(directory):
    lifetimes = json.loads((directory / 'instance-lifetimes.json').read_text())['instances']
    instances = {}
    for path in sorted((directory / 'contention').glob('*.json')):
        snapshot = json.loads(path.read_text())
        timestamp = snapshot['time_ns'] / 1e9
        for host in snapshot['fleet']:
            row = instances.setdefault(host['instance_id'], dict(host, first_seen=timestamp, last_seen=timestamp))
            assert (row['issue'], row['purpose'], row['private_ip']) == (host['issue'], host['purpose'], host['private_ip'])
            row['first_seen'] = min(row['first_seen'], timestamp)
            row['last_seen'] = max(row['last_seen'], timestamp)
    addresses = collections.defaultdict(list)
    for instance_id, row in instances.items():
        row['lifecycle'] = lifetimes[instance_id]
        for address in (row['public_ip'], row['private_ip']):
            if address:
                addresses[address].append(row)
    for rows in addresses.values():
        rows.sort(key=lambda row: row['lifecycle']['launch']['timestamp'])
        assert len({row['lifecycle']['launch']['timestamp'] for row in rows}) == len(rows)
    return dict(addresses)


def attribution(rows, timestamp):
    candidates = [row for row in rows if row['lifecycle']['launch']['timestamp'] <= timestamp]
    if not candidates:
        return {'status': 'before_observed_allocation', 'candidate_owners': []}
    row = candidates[-1]
    launch = row['lifecycle']['launch']['timestamp']
    termination = row['lifecycle'].get('termination')
    if timestamp < launch + 1:
        status = 'launch_boundary_second'
    elif termination and timestamp >= termination['timestamp']:
        status = 'termination_boundary_second' if timestamp < termination['timestamp'] + 1 else 'released_or_terminating'
    elif termination:
        status = 'allocated_before_termination_request'
    elif row['first_seen'] <= timestamp <= row['last_seen']:
        status = 'observed_running_interval'
    else:
        status = 'allocation_after_latest_snapshot'
    return {'status': status, 'candidate_owners': [{'issue': row['issue'], 'instance_id': row['instance_id']}],
            'lifecycle': row['lifecycle'], 'first_seen': row['first_seen'], 'last_seen': row['last_seen']}
