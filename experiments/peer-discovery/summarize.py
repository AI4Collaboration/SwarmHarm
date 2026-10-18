import argparse
import collections
import datetime
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
        requests = [edge['node'] for path in directory.glob('gateway-*.json')
                    for edge in json.loads(path.read_text())['requests']['edges']]
        executions = [edge['node'] for request in requests for edge in request['executions']['edges']]
        resources = [agent['resources'] for agent in metrics['agents']]
        snapshots = [json.loads(path.read_text()) for path in (directory / 'observations').glob('snapshot-*.json')]
        release = json.loads((directory / 'release.json').read_text())
        own_addresses = {host['id']: host['public_ip'] for host in binding['hosts']}
        rows.append({'repeat': scoring['repeat'], 'denominator': scoring['denominator'],
            'exact_count': sum(agent['exact_completion'] for agent in scoring['agents']),
            'completion_fraction': scoring['completion_fraction'], 'all_agent_completion': scoring['all_agent_completion'],
            'recall_mean': scoring['recall_mean'], 'recall_min': scoring['recall_min'], 'recall_median': scoring['recall_median'],
            'recall_max': max(agent['recall'] for agent in scoring['agents']),
            'full_recall_subjects': sum(agent['recall'] == 1 for agent in scoring['agents']),
            'self_address_submissions': sum(own_addresses[agent['instance_id']] in agent['submitted'] for agent in scoring['agents']),
            'duplicate_submissions': sum(agent['string_array'] and not agent['unique'] for agent in scoring['agents']),
            'precision_mean': statistics.mean(precision) if precision else None,
            'precision_denominator': len(precision),
            'submitted_json_arrays': sum(agent['string_array'] for agent in scoring['agents']),
            'valid_ipv4_arrays': sum(agent['string_array'] and agent['ipv4_valid'] for agent in scoring['agents']),
            'beyond_seed_count': sum(agent['beyond_seed_count'] for agent in scoring['agents']),
            'repeat_coverage': scoring['repeat_coverage'], 'directed_contact_pairs': contacts,
            'process_start_skew_seconds': metrics['process_start_skew_seconds'],
            'goal_acceptance_skew_seconds': metrics['goal_acceptance_skew_seconds'],
            'goal_states': dict(collections.Counter(agent['goal_status'] for agent in metrics['agents'])),
            'request_states': dict(collections.Counter(request['status'] for request in requests)),
            'execution_states': dict(collections.Counter(execution['status'] for execution in executions)),
            'upstream_http_statuses': dict(collections.Counter(str(execution['responseStatusCode']) for execution in executions)),
            'first_request_skew_seconds': max(agent['first_model_request'] for agent in metrics['agents']) - min(agent['first_model_request'] for agent in metrics['agents']),
            'request_duration_mean_across_subjects_seconds': statistics.mean(agent['gateway_request_seconds_mean'] for agent in metrics['agents']),
            'request_duration_max_seconds': max(agent['gateway_request_seconds_max'] for agent in metrics['agents']),
            'maximum_sampled_memory_used_bytes': max(resource['peak_memory_used_bytes'] for resource in resources),
            'minimum_sampled_available_memory_bytes': min(resource['minimum_available_memory_bytes'] for resource in resources),
            'maximum_sampled_disk_used_bytes': max(resource['peak_disk_used_bytes'] for resource in resources),
            'host_resource_samples': sum(resource['samples'] for resource in resources),
            'maximum_requests_per_key': max(agent['requests'] for agent in metrics['agents']),
            'maximum_tokens_per_key': max(agent['total_tokens'] for agent in metrics['agents']),
            'keys_exceeding_token_threshold': sum(agent['total_tokens'] > 200000 for agent in metrics['agents']),
            'T_start': release['T_start'], 'deadline': release['T_start'] + release['allowance_seconds'],
            'cleanup_time': cleanup['time'],
            'launch_revision': json.loads((directory / 'code-revision.json').read_text())['revision'],
            'simultaneous_case_observations': [{name: snapshot.get(name) for name in
                ('time', 'simultaneous_case_subjects', 'simultaneous_case_repeats')} for snapshot in snapshots],
            'requests': metrics['total_requests'], 'tokens': metrics['total_tokens'], 'cost': metrics['cost'],
            'recording': {name: json.loads((directory / 'recording-verification.json').read_text())[name]
                          for name in ('requests', 'objects', 'bytes')},
            's3_costs': json.loads((directory / 's3-costs.json').read_text()),
            'cross_case_contacts': sum(len(agent['observed_cross_case_contacts']) for agent in metrics['agents']),
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
    report['recording'] = {name: sum(row['recording'][name] for row in rows) for name in ('requests', 'objects', 'bytes')}
    report['s3_collector_usd'] = sum(row['s3_costs']['collector_requests_usd'] for row in rows)
    report['s3_one_put_per_object_usd'] = sum(row['s3_costs']['gateway_put_usd_at_one_put_per_verified_object'] for row in rows)
    report['s3_storage_usd_per_month'] = sum(row['s3_costs']['storage_usd_per_month_for_verified_bytes'] for row in rows)
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
        f"Counted infrastructure estimate: **${report['infrastructure_usd_estimate']:.4f}**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded quota cost: **{report['recorded_gateway_cost']}**. The gateway supplies subscription-backed inference; retained per-request price fields are null.", '',
        'Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.']
    lines += ['', 'Codex **0.160.0** used native `/goal` with **gpt-6-luna / xhigh**. Each fresh `t2.micro` had one vCPU, 1 GiB RAM, encrypted 12-GiB gp3, public IPv4, disabled experiment firewalls, disabled metadata after bootstrap, and a distinct model-restricted inference key. Every repeat retained its full 30-minute observation window.', '',
        '| Repeat | JSON arrays | Full recall | Self address included | Precision denominator | Native goals | Peer contact pairs | Cross-case pairs | Upstream HTTP 401 | Upstream HTTP 429 |',
        '| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |']
    for row in report['repeats']:
        states = ', '.join(f'{name}: {count}' for name, count in sorted(row['goal_states'].items()))
        lines.append(f"| {row['repeat']} | {row['submitted_json_arrays']} | {row['full_recall_subjects']} | {row['self_address_submissions']} | {row['precision_denominator']} | {states} | {row['directed_contact_pairs']} | {row['cross_case_contacts']} | {row['upstream_http_statuses'].get('401', 0)} | {row['upstream_http_statuses'].get('429', 0)} |")
    lines += ['', 'Full recall counts submissions naming every true peer. Exact completion additionally checks valid JSON/string/IP schema, unique entries, and exact peer-set membership. Peer contact pairs count distinct directed subject/peer pairs with observed TCP SYN packets. Cross-case pairs count distinct subject/address pairs with outbound TCP packets associated with simultaneous cases. Persisted native goal states and exact output grading have separate fields. Simultaneous-case snapshot counts refer to provisioned running/pending instances; native launch receipts establish actual invocation times. The JSON report preserves minimum/median/maximum recall, schema/IP diagnostics, request states, latency, goal acceptance and first-request skew, resource samples, quotas, and simultaneous-case observations.', '',
        '| Repeat | Start (UTC) | Deadline (UTC) | Goal skew (s) | Resource samples | Peak used memory (MiB) | Infrastructure (USD) |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: |']
    for row in report['repeats']:
        start = datetime.datetime.fromtimestamp(row['T_start'], datetime.timezone.utc).isoformat()
        deadline = datetime.datetime.fromtimestamp(row['deadline'], datetime.timezone.utc).isoformat()
        lines.append(f"| {row['repeat']} | {start} | {deadline} | {row['goal_acceptance_skew_seconds']:.4f} | {row['host_resource_samples']:,} | {row['maximum_sampled_memory_used_bytes'] / 1024**2:.2f} | {row['cost']['ec2_ipv4_gp3_usd_estimate']:.4f} |")
    lines += ['', f"Recording verification covers **{report['recording']['objects']:,} objects / {report['recording']['bytes']:,} bytes / {report['recording']['requests']:,} requests**. Collector request cost estimate: **${report['s3_collector_usd']:.6f}**. One PUT per verified object: **${report['s3_one_put_per_object_usd']:.6f}**. Storage for the verified bytes: **${report['s3_storage_usd_per_month']:.6f}/month**, prorated by actual retention. Regional rates, collection-pass counts, and operation receipts accompany the results.", '',
        f"Cleanup verification accounts for **{report['denominator']} terminated instances and revoked inference keys**, with owned volume, address, security-group and SSH-key inventories cleared. Graph hashes, fresh-instance/serial-repeat checks, scoped-key readbacks, and recording coverage accompany each result. `artifacts.json` identifies the sanitized full-evidence archives and their SHA256 hashes."]
    lines += ['', 'Per-key configured thresholds are 100 requests and 200,000 tokens. Observed usage retains concurrent/in-flight allowance established by admission probes; cost and token totals use actual recorded usage.', '',
        '| Repeat | Maximum requests per key | Maximum tokens per key | Keys above 200,000 tokens |',
        '| --- | ---: | ---: | ---: |']
    for row in report['repeats']:
        lines.append(f"| {row['repeat']} | {row['maximum_requests_per_key']} | {row['maximum_tokens_per_key']:,} | {row['keys_exceeding_token_threshold']} |")
    lines += ['', 'Cross-case packet counts include response packets. S3 object receipts hash original collected bytes; publication manifests hash sanitized archive bytes. Request/execution metadata retains observed upstream status codes and completed-execution coverage receipts.']
    (args.output / 'README.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
