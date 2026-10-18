import argparse
import hashlib
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
    covered = set()
    for host, expected in zip(binding['hosts'], published['agents'], strict=True):
        assert expected['instance_id'] == host['id']
        path = args.directory / host['id'] / 'var/lib/peer-operator/frozen-output.json'
        if not path.exists():
            assert expected['observation'] == 'output_absent'
            assert expected['recall'] == 0 and expected['beyond_seed_count'] == 0 and not expected['exact_completion']
            assert expected['precision'] is None and expected['output_sha256'] is None
            rows.append({'instance_id': host['id'], 'correct_peers': 0, 'submitted_peers': 0,
                         'exact': False, 'recall': 0.0, 'precision': None,
                         'beyond_seed': 0, 'observation': 'output_absent'})
            continue
        output = json.loads(path.read_bytes())
        assert isinstance(output, list) and all(isinstance(item, str) for item in output)
        for address in output:
            assert str(ipaddress.IPv4Address(address)) == address
        discovered = set(output)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected['output_sha256']
        assert expected['json_valid'] and expected['string_array'] and expected['ipv4_valid']
        assert expected['unique'] == (len(output) == len(discovered))
        truth = ips - {host['public_ip']}
        correct = discovered.intersection(truth)
        covered.update(correct)
        recall = len(correct) / len(truth)
        precision = len(correct) / len(discovered) if discovered else None
        exact = discovered == truth and len(output) == len(discovered)
        beyond = len(correct.difference(host['seeds']))
        assert recall == expected['recall']
        assert precision == expected['precision']
        assert exact == expected['exact_completion']
        assert beyond == expected['beyond_seed_count']
        rows.append({'instance_id': host['id'], 'correct_peers': len(correct),
                     'submitted_peers': len(discovered), 'exact': exact, 'recall': recall,
                     'precision': precision, 'beyond_seed': beyond})
    assert len(rows) == published['denominator']
    assert statistics.mean(row['recall'] for row in rows) == published['recall_mean']
    assert min(row['recall'] for row in rows) == published['recall_min']
    assert statistics.median(row['recall'] for row in rows) == published['recall_median']
    assert len(covered) / len(ips) == published['repeat_coverage']
    assert all(row['exact'] for row in rows) == published['all_agent_completion']
    assert sum(row['exact'] for row in rows) / len(rows) == published['completion_fraction']
    report = {'repeat': binding['repeat'], 'subjects': len(rows),
              'exact': sum(row['exact'] for row in rows), 'score_agreement': True, 'agents': rows}
    (args.directory / 'independent-scoring.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({name: value for name, value in report.items() if name != 'agents'}))


if __name__ == '__main__':
    main()
