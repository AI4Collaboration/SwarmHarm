import argparse
import hashlib
import ipaddress
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audit', type=Path)
    parser.add_argument('--fleet-directory', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.audit.read_text())
    histories = []
    for directory in args.fleet_directory:
        cloud_path = directory / 'cloud.json'
        cloud = json.loads(cloud_path.read_text())
        cleanup_path = directory / 'cleanup.json'
        cleanup = json.loads(cleanup_path.read_text()) if cleanup_path.exists() else None
        histories.append({'issue': cloud['issue'], 'purpose': cloud['purpose'],
            'created_at': cloud['created_at'], 'cleanup_time': cleanup['time'] if cleanup else None,
            'hosts': cloud['hosts'], 'cloud_sha256': hashlib.sha256(cloud_path.read_bytes()).hexdigest(),
            'cleanup_sha256': hashlib.sha256(cleanup_path.read_bytes()).hexdigest() if cleanup else None})
    reconciled = 0
    for row in report['cross_case_records']:
        if not ipaddress.IPv4Address(row['remote_raw_ip']).is_private:
            continue
        matches = [(history, host) for history in histories for host in history['hosts']
                   if host['private_ip'] == row['remote_raw_ip']
                   and history['created_at'] <= row['first_packet']
                   and (history['cleanup_time'] is None or row['last_packet'] <= history['cleanup_time'])]
        if not matches:
            continue
        assert len(matches) == 1, (row['remote_raw_ip'], row['first_packet'])
        history, host = matches[0]
        row.update({'remote_public_ip': host['public_ip'], 'context_instance_id': host['id'],
                    'context_issue': history['issue'], 'context_purpose': history['purpose'],
                    'attribution_basis': f'fleet_lifetime:{history["cloud_sha256"]}'})
        reconciled += 1
    for key, total in report['cross_case_totals'].items():
        window, direction = key.rsplit('_', 1)
        selected = [row for row in report['cross_case_records']
                    if row['window'] == window and row['direction'] == direction]
        total['context_cases'] = sorted({row['context_issue'] for row in selected})
    report['fleet_identity_records'] = reconciled
    report['fleet_identity_evidence'] = histories
    report['attribution'] = 'Fleet creation and cleanup receipts identify private addresses within each recorded lifetime; remaining identities use timestamped context snapshots. TCP direction and the subject deadline define contact counts.'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'fleet_identity_records': reconciled,
                      'identities': sorted({(row['context_issue'], row.get('context_purpose'),
                                             row['context_instance_id'], row['remote_public_ip'])
                                            for row in report['cross_case_records']})}))


if __name__ == '__main__':
    main()
