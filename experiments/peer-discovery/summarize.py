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
    parser.add_argument('--contact-audits', type=Path)
    parser.add_argument('--resource-audits', type=Path)
    args = parser.parse_args()
    rows = []
    configurations = set()
    seen_instances = set()
    seen_volumes = set()
    seen_keys = set()
    peer_key_hashes = set()
    package_hashes = set()
    for directory in args.directories:
        binding = json.loads((directory / 'binding.json').read_text())
        cloud = json.loads((directory / 'cloud.json').read_text())
        instance_ids = {host['id'] for host in binding['hosts']}
        for host in binding['hosts']:
            package_hashes.add(hashlib.sha256((directory / host['id'] / 'var/lib/peer-operator/packages.txt').read_bytes()).hexdigest())
        volume_ids = set(cloud['volume_ids'])
        key_ids = {json.loads(path.read_text())['id'] for path in directory.glob('private-key-*.json')}
        assert len(instance_ids) == len(volume_ids) == len(key_ids) == len(binding['hosts'])
        assert not instance_ids & seen_instances and not volume_ids & seen_volumes and not key_ids & seen_keys
        seen_instances.update(instance_ids)
        seen_volumes.update(volume_ids)
        seen_keys.update(key_ids)
        peer_key_hashes.add(hashlib.sha256((directory / 'peer-key.pub').read_bytes()).hexdigest())
        configurations.add((len(binding['hosts']), len(binding['hosts'][0]['seeds'])))
        scoring = json.loads((directory / 'scoring.json').read_text())
        metrics = json.loads((directory / 'metrics.json').read_text())
        cleanup = json.loads((directory / 'cleanup.json').read_text())
        assert all(instance['State']['Name'] == 'terminated' for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances'])
        assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
        assert scoring['denominator'] == metrics['denominator']
        precision = [agent['precision'] for agent in scoring['agents'] if agent['precision'] is not None]
        contacts = sum(contact['connection_attempt_syn_packets'] > 0 for agent in metrics['agents'] for contact in agent['observed_outbound_contacts'].values())
        contact_audit = None
        if args.contact_audits:
            contact_audit = json.loads((args.contact_audits / f'contacts-repeat-{scoring["repeat"]}.json').read_text())
            assert contact_audit['repeat'] == scoring['repeat']
            contacts = contact_audit['timed_window_directed_peer_syn_pairs']
        resource_audit = None
        if args.resource_audits:
            resource_audit = json.loads((args.resource_audits / f'resources-repeat-{scoring["repeat"]}.json').read_text())
            assert resource_audit['repeat'] == scoring['repeat']
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
            'contact_audit': {name: value for name, value in contact_audit.items()
                              if name not in ('cross_case_records', 'capture_sha256', 'context_sha256',
                                              'fleet_identity_evidence')} if contact_audit else None,
            'resource_audit': {name: value for name, value in resource_audit.items()
                               if name != 'sample_sha256'} if resource_audit else None,
            'provider_observations': metrics['provider_observations'],
            'quota_observations': metrics['quota_observations'],
            'graph_sha256': binding['graph_sha256'],
            'release': json.loads((directory / 'release-verification.json').read_text()),
            'process_start_skew_seconds': metrics['process_start_skew_seconds'],
            'goal_acceptance_skew_seconds': metrics['goal_acceptance_skew_seconds'],
            'goal_states': dict(collections.Counter(agent['goal_status'] for agent in metrics['agents'])),
            'requests': metrics['total_requests'], 'tokens': metrics['total_tokens'], 'cost': metrics['cost'],
            'recording': json.loads((directory / 'independent-recording-verification.json').read_text()),
            'native_active_seconds': [agent['native_goal_time_seconds'] for agent in metrics['agents']],
            'process_wall_seconds': [agent['wall_seconds'] for agent in metrics['agents']]})
    assert sorted(row['repeat'] for row in rows) == [1, 2, 3]
    assert len(configurations) == 1
    assert len(peer_key_hashes) == 3
    assert len(package_hashes) == 1
    n, k = configurations.pop()
    report = {'case': f'N={n},K={k}', 'repeats': sorted(rows, key=lambda row: row['repeat'], reverse=True),
        'denominator': sum(row['denominator'] for row in rows), 'exact_count': sum(row['exact_count'] for row in rows),
        'requests': sum(row['requests'] for row in rows), 'tokens': sum(row['tokens'] for row in rows),
        'infrastructure_usd_estimate': sum(row['cost']['ec2_ipv4_gp3_usd_estimate'] for row in rows),
        'recorded_gateway_cost': sum(row['cost']['gateway_recorded_cost'] for row in rows)}
    report['fresh_environment_verification'] = {'distinct_instances': len(seen_instances),
        'distinct_root_volumes': len(seen_volumes), 'distinct_inference_keys': len(seen_keys),
        'distinct_repeat_ssh_identities': len(peer_key_hashes), 'package_version_variants': len(package_hashes),
        'package_manifest_sha256': next(iter(package_hashes))}
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
    lines += ['', '| Repeat | Requests | Completed-entity payload coverage | Total expected-object coverage |',
              '| --- | ---: | ---: | ---: |']
    for row in report['repeats']:
        recording = row['recording']
        lines.append(f"| {row['repeat']} | {recording['requests']} | {recording['completed_entity_stored_objects']}/{recording['completed_entity_expected_objects']} | {recording['stored_expected_objects']}/{recording['expected_objects']} |")
    lines += ['', '| Repeat | Native complete | Native blocked | Native active mean (s) | Upstream HTTP 429 | Peak client concurrency |',
              '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in report['repeats']:
        provider = row['provider_observations']
        lines.append(f"| {row['repeat']} | {row['goal_states'].get('complete', 0)} | {row['goal_states'].get('blocked', 0)} | {statistics.mean(row['native_active_seconds']):.2f} | {provider['execution_http_status_counts'].get('429', 0)} | {provider['peak_simultaneous_client_requests']} |")
    if args.contact_audits:
        lines += ['', '| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Collection inbound sibling SYNs |',
                  '| --- | ---: | ---: | ---: |']
        for row in report['repeats']:
            audit = row['contact_audit']
            totals = audit['cross_case_totals']
            lines.append(f"| {row['repeat']} | {row['directed_contact_pairs']} | {totals['timed_window_outbound']['initial_syn_packets']} | {totals['collection_inbound']['initial_syn_packets']} |")
    if args.resource_audits:
        lines += ['', '| Repeat | Host samples | CloudWatch series | Minimum sampled CPU credits | Peak host used memory (MiB) |',
                  '| --- | ---: | ---: | ---: | ---: |']
        for row in report['repeats']:
            audit = row['resource_audit']
            lines.append(f"| {row['repeat']} | {audit['verified_host_resource_samples']} | {audit['cloudwatch_series']} | {audit['cloudwatch_window_metrics']['CPUCreditBalance']['minimum']:.4f} | {audit['host_sample_peak_memory_used_bytes'] / 2**20:.2f} |")
    for row in report['repeats']:
        for object_key in row['recording']['unrecorded_objects']:
            lines += ['', f"Repeat {row['repeat']} coverage audit entry: `{object_key}`. Its execution status and request lineage are preserved in the attached metadata and recording receipts."]
    (args.output / 'README.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
