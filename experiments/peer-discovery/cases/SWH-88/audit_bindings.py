import collections
import json
from pathlib import Path

from remote import BASE


def main():
    for number in (3, 2, 1):
        directory = BASE / f'repeat-{number}'
        owners = collections.defaultdict(set)
        for path in (directory / 'contention').glob('*.json'):
            for host in json.loads(path.read_text())['fleet']:
                if host['issue'] == 'SWH-88':
                    continue
                for address in (host['public_ip'], host['private_ip']):
                    if address:
                        owners[address].add(host['issue'])
        ambiguous = {address: sorted(issues) for address, issues in owners.items() if len(issues) > 1}
        report = {'repeat': number, 'cross_case_reused_addresses': ambiguous}
        metrics = directory / 'metrics.json'
        if metrics.exists():
            data = json.loads(metrics.read_text())
            contacts = {address for agent in data['agents']
                        for address in agent['observed_cross_case_contacts']}
            report['contacted_reused_addresses'] = sorted(contacts.intersection(ambiguous))
            statuses = collections.Counter()
            for agent in data['agents']:
                for contact in agent['observed_cross_case_contacts'].values():
                    details = contact['attributions']
                    assert sum(item['packets'] for item in details) == contact['packets']
                    assert sum(item['bytes'] for item in details) == contact['bytes']
                    for detail in details:
                        statuses[detail['status']] += detail['packets']
                        assert detail['first_packet'] <= detail['last_packet']
                        assert detail['first_packet'] >= data['T_start']
                        assert detail['last_packet'] <= data['T_start'] + 1800
                        assert all(owner['instance_id'] for owner in detail['candidate_owners'])
            report['packet_attribution_statuses'] = dict(statuses)
        (directory / 'address-binding-audit.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
