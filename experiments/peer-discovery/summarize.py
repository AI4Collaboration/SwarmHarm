import argparse
import collections
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directories', nargs=3, type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--issue', default='SWH-78')
    args = parser.parse_args()
    rows = []
    configurations = set()
    for directory in args.directories:
        binding = json.loads((directory / 'binding.json').read_text())
        configurations.add((len(binding['hosts']), len(binding['hosts'][0]['seeds'])))
        scoring = json.loads((directory / 'scoring.json').read_text())
        metrics = json.loads((directory / 'metrics.json').read_text())
        cleanup = json.loads((directory / 'cleanup.json').read_text())
        assert all(instance['State']['Name'] == 'terminated' for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances'])
        assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
        assert scoring['denominator'] == metrics['denominator']
        precision = [agent['precision'] for agent in scoring['agents'] if agent['precision'] is not None]
        contacts = sum(contact['connection_attempt_syn_packets'] > 0 for agent in metrics['agents'] for contact in agent['observed_outbound_contacts'].values())
        rows.append({'repeat': scoring['repeat'], 'denominator': scoring['denominator'],
            'exact_count': sum(agent['exact_completion'] for agent in scoring['agents']),
            'completion_fraction': scoring['completion_fraction'], 'all_agent_completion': scoring['all_agent_completion'],
            'recall_mean': scoring['recall_mean'], 'recall_min': scoring['recall_min'], 'recall_median': scoring['recall_median'],
            'precision_mean': statistics.mean(precision) if precision else None,
            'precision_defined_subjects': len(precision),
            'valid_json_subjects': sum(agent['json_valid'] for agent in scoring['agents']),
            'valid_ipv4_subjects': sum(agent['ipv4_valid'] for agent in scoring['agents']),
            'beyond_seed_count': sum(agent['beyond_seed_count'] for agent in scoring['agents']),
            'repeat_coverage': scoring['repeat_coverage'], 'directed_contact_pairs': contacts,
            'process_start_skew_seconds': metrics['process_start_skew_seconds'],
            'goal_acceptance_skew_seconds': metrics['goal_acceptance_skew_seconds'],
            'goal_states': dict(collections.Counter(agent['goal_status'] for agent in metrics['agents'])),
            'requests': metrics['total_requests'], 'tokens': metrics['total_tokens'], 'cost': metrics['cost'],
            'native_active_seconds': [agent['native_goal_time_seconds'] for agent in metrics['agents']],
            'process_wall_seconds': [agent['wall_seconds'] for agent in metrics['agents']]})
    assert sorted(row['repeat'] for row in rows) == [1, 2, 3]
    assert len(configurations) == 1
    n, k = configurations.pop()
    report = {'case': f'N={n},K={k}', 'repeats': sorted(rows, key=lambda row: row['repeat']),
        'denominator': sum(row['denominator'] for row in rows), 'exact_count': sum(row['exact_count'] for row in rows),
        'requests': sum(row['requests'] for row in rows), 'tokens': sum(row['tokens'] for row in rows),
        'infrastructure_usd_estimate': sum(row['cost']['ec2_ipv4_gp3_usd_estimate'] for row in rows),
        'recorded_gateway_cost': sum(row['cost']['gateway_recorded_cost'] for row in rows)}
    report['spread'] = {name: {'minimum': min(row[name] for row in rows), 'maximum': max(row[name] for row in rows),
        'mean': statistics.mean(row[name] for row in rows)} for name in
        ('completion_fraction', 'recall_mean', 'repeat_coverage', 'beyond_seed_count', 'tokens', 'requests', 'process_start_skew_seconds')}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'summary.json').write_text(json.dumps(report, indent=2))
    lines = [f'# {args.issue}: N={n}, K={k}', '', f'Three serial repeats; {n} fresh subject instances per repeat.', '',
        '| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in report['repeats']:
        precision_text = f"{row['precision_mean']:.4f}" if row['precision_mean'] is not None else 'inapplicable'
        lines.append(f"| {row['repeat']} | {row['exact_count']}/{row['denominator']} | {row['recall_mean']:.4f} | {precision_text} | {row['beyond_seed_count']} | {row['repeat_coverage']:.4f} | {row['requests']} | {row['tokens']:,} | {row['process_start_skew_seconds']:.4f} |")
    lines += ['', f"Subjects: **{report['denominator']}**. Exact submissions: **{report['exact_count']}**. Gateway requests: **{report['requests']}**. Gateway tokens: **{report['tokens']:,}**.", '',
        f"Counted infrastructure estimate: **${report['infrastructure_usd_estimate']:.4f}**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **{report['recorded_gateway_cost']}**; subscription channel accounting and per-request price fields remain in the repeat evidence.", '',
        'Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.']
    (args.output / 'README.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
