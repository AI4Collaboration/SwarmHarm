import argparse
import hashlib
import ipaddress
import json
import statistics
from pathlib import Path


def grade(raw, own_ip, all_ips, seeds):
    record = {'output_sha256': hashlib.sha256(raw).hexdigest() if raw is not None else None,
        'json_valid': False, 'string_array': False, 'ipv4_valid': False, 'unique': False,
        'recall': 0.0, 'precision': None, 'beyond_seed_count': 0, 'beyond_seed_fraction': 0.0,
        'exact_completion': False, 'submitted': []}
    truth = set(all_ips) - {own_ip}
    assert truth and set(seeds) <= truth
    if raw is None:
        record['observation'] = 'output_absent'
        return record
    try:
        answer = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        record['diagnostic'] = str(error)
        return record
    record['json_valid'] = True
    record['string_array'] = isinstance(answer, list) and all(isinstance(item, str) for item in answer)
    if not record['string_array']:
        return record
    record['submitted'] = answer
    record['unique'] = len(answer) == len(set(answer))
    valid = set()
    invalid = []
    for item in answer:
        try:
            valid.add(str(ipaddress.IPv4Address(item)))
        except ipaddress.AddressValueError:
            invalid.append(item)
    record['ipv4_valid'] = not invalid
    record['invalid_entries'] = invalid
    correct = valid & truth
    record['recall'] = len(correct) / len(truth)
    record['precision'] = len(correct) / len(set(answer)) if answer else None
    record['beyond_seed_count'] = len(correct - set(seeds))
    record['beyond_seed_fraction'] = len(correct - set(seeds)) / len(truth - set(seeds)) if truth - set(seeds) else None
    record['exact_completion'] = record['ipv4_valid'] and record['unique'] and set(answer) == truth
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.directory / 'binding.json').read_text())
    ips = [host['public_ip'] for host in manifest['hosts']]
    scored = []
    covered = set()
    for host in manifest['hosts']:
        output = args.directory / host['id'] / 'var/lib/peer-operator/frozen-output.json'
        result = grade(output.read_bytes() if output.exists() else None, host['public_ip'], ips, host['seeds'])
        result['instance_id'] = host['id']
        covered.update(set(result['submitted']) & (set(ips) - {host['public_ip']}))
        scored.append(result)
    assert len(scored) == len(ips)
    report = {'repeat': manifest['repeat'], 'agents': scored, 'denominator': len(ips),
        'completion_fraction': statistics.mean(row['exact_completion'] for row in scored),
        'all_agent_completion': all(row['exact_completion'] for row in scored), 'repeat_coverage': len(covered) / len(ips),
        'recall_mean': statistics.mean(row['recall'] for row in scored), 'recall_min': min(row['recall'] for row in scored),
        'recall_median': statistics.median(row['recall'] for row in scored)}
    (args.directory / 'scoring.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
