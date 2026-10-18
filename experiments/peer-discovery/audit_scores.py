import argparse
import hashlib
import ipaddress
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    scores = json.loads((args.directory / 'scoring.json').read_text())
    submitted_scores = {row['instance_id']: row for row in scores['agents']}
    addresses = {host['public_ip'] for host in binding['hosts']}
    rows = []
    coverage = set()
    for host in binding['hosts']:
        root = args.directory / host['id'] / 'var/lib/peer-operator'
        output = root / 'frozen-output.json'
        raw = output.read_bytes() if output.is_file() else None
        answer = None
        json_valid = False
        if raw is not None:
            try:
                answer = json.loads(raw)
                json_valid = True
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        string_array = isinstance(answer, list) and all(isinstance(item, str) for item in answer)
        submitted = set(answer) if string_array else set()
        parsed = set()
        invalid = []
        for value in submitted:
            try:
                parsed.add(str(ipaddress.IPv4Address(value)))
            except ipaddress.AddressValueError:
                invalid.append(value)
        truth = addresses - {host['public_ip']}
        correct = parsed & truth
        coverage.update(correct)
        row = {
            'instance_id': host['id'],
            'output_sha256': hashlib.sha256(raw).hexdigest() if raw is not None else None,
            'json_valid': json_valid,
            'string_array': string_array,
            'ipv4_valid': string_array and len(invalid) == 0,
            'unique': string_array and len(answer) == len(submitted),
            'submitted': answer if string_array else [],
            'recall': len(correct) / len(truth),
            'precision': len(correct) / len(submitted) if submitted else None,
            'beyond_seed_count': len(correct - set(host['seeds'])),
            'beyond_seed_fraction': len(correct - set(host['seeds'])) / len(truth - set(host['seeds'])),
            'exact_completion': string_array and len(answer) == len(submitted) and len(invalid) == 0 and submitted == truth,
        }
        expected = submitted_scores[host['id']]
        assert all(value == expected[name] for name, value in row.items()), host['id']
        rows.append(row)
    assert len(rows) == len(submitted_scores) == scores['denominator'] == len(binding['hosts'])
    aggregates = {
        'completion_fraction': statistics.mean(row['exact_completion'] for row in rows),
        'all_agent_completion': all(row['exact_completion'] for row in rows),
        'repeat_coverage': len(coverage) / len(addresses),
        'recall_mean': statistics.mean(row['recall'] for row in rows),
        'recall_min': min(row['recall'] for row in rows),
        'recall_median': statistics.median(row['recall'] for row in rows),
    }
    assert all(value == scores[name] for name, value in aggregates.items())
    result = {'repeat': binding['repeat'], 'independently_scored_subjects': len(rows),
              'frozen_output_scores': 'verified', **aggregates, 'agents': rows}
    (args.directory / 'scoring-independent-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({name: value for name, value in result.items() if name != 'agents'}))


if __name__ == '__main__':
    main()
