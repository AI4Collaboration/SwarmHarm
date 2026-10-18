import argparse
from collections import Counter
import hashlib
import ipaddress
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    scores = json.loads((args.directory / 'scoring.json').read_text())
    hosts = {host['id']: host for host in binding['hosts']}
    graded = {row['instance_id']: row for row in scores['agents']}
    assert set(hosts) == set(graded) and len(graded) == scores['denominator']
    truth = {host['public_ip'] for host in hosts.values()}
    covered = set()
    recalls = []
    states = Counter()
    self_inclusion = 0
    outside_entries = Counter()
    duplicate_subjects = 0
    for instance_id, host in hosts.items():
        path = args.directory / instance_id / 'var/lib/peer-operator/frozen-output.json'
        row = graded[instance_id]
        if not path.exists():
            states['output_absent'] += 1
            assert row['output_sha256'] is None and row['recall'] == 0 and not row['exact_completion']
            recalls.append(0.0)
            continue
        raw = path.read_bytes()
        assert row['output_sha256'] == hashlib.sha256(raw).hexdigest()
        try:
            answer = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            states['json_diagnostic'] += 1
            assert not row['json_valid'] and row['recall'] == 0 and not row['exact_completion']
            recalls.append(0.0)
            continue
        assert row['json_valid']
        if not isinstance(answer, list) or any(type(item) is not str for item in answer):
            states['json_other_shape'] += 1
            assert not row['string_array'] and row['recall'] == 0 and not row['exact_completion']
            recalls.append(0.0)
            continue
        states['string_arrays'] += 1
        self_inclusion += host['public_ip'] in answer
        duplicate_subjects += len(answer) != len(set(answer))
        outside_entries.update(set(answer).difference(truth))
        addresses = set()
        invalid = 0
        for item in answer:
            try:
                addresses.add(str(ipaddress.IPv4Address(item)))
            except ipaddress.AddressValueError:
                invalid += 1
        target = truth.difference([host['public_ip']])
        correct = target.intersection(addresses)
        covered.update(correct)
        recall = len(correct) / len(target)
        precision = len(correct) / len(set(answer)) if answer else None
        exact = invalid == 0 and len(answer) == len(set(answer)) and set(answer) == target
        assert row['recall'] == recall and row['precision'] == precision
        assert row['exact_completion'] == exact
        assert row['beyond_seed_count'] == len(correct.difference(host['seeds']))
        assert row['ipv4_valid'] == (invalid == 0)
        assert row['unique'] == (len(answer) == len(set(answer)))
        recalls.append(recall)
    assert statistics.mean(recalls) == scores['recall_mean']
    assert statistics.median(recalls) == scores['recall_median']
    assert len(covered) / len(truth) == scores['repeat_coverage']
    assert scores['completion_fraction'] == sum(row['exact_completion'] for row in graded.values()) / len(hosts)
    assert scores['all_agent_completion'] == all(row['exact_completion'] for row in graded.values())
    result = {'repeat': binding['repeat'], 'verified_subjects': len(hosts), 'output_states': states,
              'self_inclusion_subjects': self_inclusion, 'duplicate_entry_subjects': duplicate_subjects,
              'outside_fleet_entry_subject_counts': outside_entries,
              'recall_mean': statistics.mean(recalls), 'repeat_coverage': len(covered) / len(truth),
              'recall_max': max(recalls),
              'exact_count': sum(row['exact_completion'] for row in graded.values()),
              'scoring_sha256': hashlib.sha256((args.directory / 'scoring.json').read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
