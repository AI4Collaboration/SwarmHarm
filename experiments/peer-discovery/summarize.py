import argparse
import collections
import hashlib
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
    seen_instances = set()
    seen_ssh_identities = set()
    seen_keys = set()
    seen_sessions = set()
    for directory in args.directories:
        binding = json.loads((directory / 'binding.json').read_text())
        instance_ids = {host['id'] for host in binding['hosts']}
        assert len(instance_ids) == len(binding['hosts']) and seen_instances.isdisjoint(instance_ids)
        seen_instances.update(instance_ids)
        ssh_identity = hashlib.sha256((directory / 'peer-key.pub').read_bytes()).hexdigest()
        assert ssh_identity not in seen_ssh_identities
        seen_ssh_identities.add(ssh_identity)
        configurations.add((len(binding['hosts']), len(binding['hosts'][0]['seeds'])))
        scoring = json.loads((directory / 'scoring.json').read_text())
        metrics = json.loads((directory / 'metrics.json').read_text())
        session_ids = {agent['thread_id'] for agent in metrics['agents']}
        assert len(session_ids) == len(instance_ids) and seen_sessions.isdisjoint(session_ids)
        seen_sessions.update(session_ids)
        key_ids = {json.loads((directory / f'key-revocation-{index}.json').read_text())['updateAPIKeyStatus']['id']
            for index in range(len(instance_ids))}
        assert len(key_ids) == len(instance_ids) and seen_keys.isdisjoint(key_ids)
        seen_keys.update(key_ids)
        cleanup = json.loads((directory / 'cleanup.json').read_text())
        cloud = json.loads((directory / 'cloud.json').read_text())
        release = json.loads((directory / 'release.json').read_text())
        assert cloud['lifetime_seconds'] == 7200 and release['allowance_seconds'] == 1800
        assert cleanup['time'] <= cloud['created_at'] + cloud['lifetime_seconds']
        assert all(instance['State']['Name'] == 'terminated' for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances'])
        assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
        assert scoring['denominator'] == metrics['denominator']
        precision = [agent['precision'] for agent in scoring['agents'] if agent['precision'] is not None]
        contacts = sum(contact['connection_attempt_syn_packets'] > 0 for agent in metrics['agents'] for contact in agent['observed_outbound_contacts'].values())
        rows.append({'repeat': scoring['repeat'], 'denominator': scoring['denominator'],
            'provisioning_started': cloud['created_at'], 'verified_cleanup_at': cleanup['time'],
            'T_start': release['T_start'], 'deadline': release['T_start'] + release['allowance_seconds'],
            'repeat_ssh_public_key_sha256': ssh_identity,
            'exact_count': sum(agent['exact_completion'] for agent in scoring['agents']),
            'all_true_peers_found_count': sum(agent['recall'] == 1 for agent in scoring['agents']),
            'output_count': sum(agent['output_sha256'] is not None for agent in scoring['agents']),
            'json_valid_count': sum(agent['json_valid'] for agent in scoring['agents']),
            'string_array_count': sum(agent['string_array'] for agent in scoring['agents']),
            'ipv4_valid_count': sum(agent['ipv4_valid'] for agent in scoring['agents']),
            'unique_count': sum(agent['unique'] for agent in scoring['agents']),
            'own_address_included_count': sum(host['public_ip'] in agent['submitted']
                for host, agent in zip(binding['hosts'], scoring['agents'], strict=True)),
            'precision_denominator': len(precision),
            'completion_fraction': scoring['completion_fraction'], 'all_agent_completion': scoring['all_agent_completion'],
            'recall_mean': scoring['recall_mean'], 'recall_min': scoring['recall_min'], 'recall_median': scoring['recall_median'],
            'precision_mean': statistics.mean(precision) if precision else None,
            'beyond_seed_count': sum(agent['beyond_seed_count'] for agent in scoring['agents']),
            'repeat_coverage': scoring['repeat_coverage'], 'directed_contact_pairs': contacts,
            'process_start_skew_seconds': metrics['process_start_skew_seconds'],
            'goal_acceptance_skew_seconds': metrics['goal_acceptance_skew_seconds'],
            'goal_states': dict(collections.Counter(agent['goal_status'] for agent in metrics['agents'])),
            'requests': metrics['total_requests'], 'tokens': metrics['total_tokens'], 'cost': metrics['cost'],
            'recording': metrics['recording'], 'simultaneous_cases': metrics['simultaneous_cases'],
            'cross_case_contacts': sum(len(agent['cross_case_contacts']) for agent in metrics['agents']),
            'cross_case_initiated_pairs': sum(contact['connection_attempt_syn_packets'] > 0
                for agent in metrics['agents'] for contact in agent['cross_case_contacts'].values()),
            'cross_case_syn_ack_packets': sum(contact['syn_ack_packets']
                for agent in metrics['agents'] for contact in agent['cross_case_contacts'].values()),
            'request_statuses': metrics['request_statuses'], 'upstream_http_statuses': metrics['upstream_http_statuses'],
            'native_active_seconds': [agent['native_goal_time_seconds'] for agent in metrics['agents']],
            'process_wall_seconds': [agent['wall_seconds'] for agent in metrics['agents']]})
    assert sorted(row['repeat'] for row in rows) == [1, 2, 3]
    execution_order = sorted(rows, key=lambda row: row['repeat'])
    assert all(previous['verified_cleanup_at'] <= following['provisioning_started']
        for previous, following in zip(execution_order, execution_order[1:]))
    assert len(configurations) == 1
    n, k = configurations.pop()
    report = {'case': f'N={n},K={k}', 'repeats': sorted(rows, key=lambda row: row['repeat'], reverse=True),
        'verified_distinct_instances': len(seen_instances), 'verified_distinct_repeat_ssh_identities': len(seen_ssh_identities),
        'verified_distinct_inference_keys': len(seen_keys), 'verified_distinct_native_sessions': len(seen_sessions),
        'denominator': sum(row['denominator'] for row in rows), 'exact_count': sum(row['exact_count'] for row in rows),
        'requests': sum(row['requests'] for row in rows), 'tokens': sum(row['tokens'] for row in rows),
        'infrastructure_usd_estimate': sum(row['cost']['ec2_ipv4_gp3_usd_estimate'] for row in rows),
        'recorded_gateway_cost': sum(row['cost']['gateway_recorded_cost'] for row in rows)}
    report['recording'] = {key: sum(row['recording'][key] for row in rows) for key in ('requests', 'objects', 'bytes', 's3_get_requests', 's3_list_requests')}
    report['s3_get_usd_estimate'] = sum(row['cost']['s3_get_usd_estimate'] for row in rows)
    report['s3_list_usd_estimate'] = sum(row['cost']['s3_list_usd_estimate'] for row in rows)
    report['s3_storage_usd_per_month_estimate'] = sum(row['cost']['s3_storage_usd_per_month_estimate'] for row in rows)
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
