import collections
import json
from pathlib import Path

from remote import BASE


def main():
    for number in (1, 2):
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
            contacts = {address for agent in json.loads(metrics.read_text())['agents']
                        for address in agent['observed_cross_case_contacts']}
            report['contacted_reused_addresses'] = sorted(contacts.intersection(ambiguous))
        (directory / 'address-binding-audit.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
