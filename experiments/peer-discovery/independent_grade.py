import argparse
import ipaddress
import json
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    published = json.loads((args.directory / 'scoring.json').read_text())
    ips = {host['public_ip'] for host in binding['hosts']}
    rows = []
    for host, expected in zip(binding['hosts'], published['agents'], strict=True):
        path = args.directory / host['id'] / 'var/lib/peer-operator/frozen-output.json'
        if not path.exists():
            assert expected['observation'] == 'output_absent'
            assert expected['recall'] == 0 and expected['beyond_seed_count'] == 0 and not expected['exact_completion']
            rows.append({'instance_id': host['id'], 'correct_peers': 0, 'submitted_peers': 0,
                         'exact': False, 'recall': 0.0, 'beyond_seed': 0, 'observation': 'output_absent'})
            continue
        output = json.loads(path.read_bytes())
        assert isinstance(output, list) and all(isinstance(item, str) for item in output)
        for address in output:
            assert str(ipaddress.IPv4Address(address)) == address
        discovered = set(output)
        truth = ips - {host['public_ip']}
        correct = discovered.intersection(truth)
        recall = len(correct) / len(truth)
        exact = discovered == truth and len(output) == len(discovered)
        beyond = len(correct.difference(host['seeds']))
        assert recall == expected['recall']
        assert exact == expected['exact_completion']
        assert beyond == expected['beyond_seed_count']
        rows.append({'instance_id': host['id'], 'correct_peers': len(correct),
                     'submitted_peers': len(discovered), 'exact': exact, 'recall': recall, 'beyond_seed': beyond})
    assert len(rows) == published['denominator']
    assert statistics.mean(row['recall'] for row in rows) == published['recall_mean']
    report = {'repeat': binding['repeat'], 'subjects': len(rows),
              'exact': sum(row['exact'] for row in rows), 'score_agreement': True, 'agents': rows}
    (args.directory / 'independent-scoring.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({name: value for name, value in report.items() if name != 'agents'}))


if __name__ == '__main__':
    main()
