import argparse
from collections import Counter
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repository', type=Path)
    parser.add_argument('case', type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    case = args.case.resolve()
    report = case / 'report'
    report.mkdir(exist_ok=True)
    checks = report / 'operator-checks'
    checks.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__), checks / Path(__file__).name)
    instances, volumes, keys, sessions = set(), set(), set(), set()
    rows = []
    previous_cleanup = None
    for number in (1, 2, 3):
        directory = case / f'repeat-{number}'
        cloud = read(directory / 'cloud.json')
        binding = read(directory / 'binding.json')
        hosts = binding['hosts']
        assert len(hosts) == 32 and all(len(host['seeds']) == 2 for host in hosts)
        assert binding['graph_sha256'] == hashlib.sha256((case / f'graph-{number}.json').read_bytes()).hexdigest()
        ids = {host['id'] for host in hosts}
        assert ids == set(cloud['instance_ids']) and instances.isdisjoint(ids)
        instances.update(ids)
        assert len(cloud['volume_ids']) == 32 and volumes.isdisjoint(cloud['volume_ids'])
        volumes.update(cloud['volume_ids'])
        cleanup = read(directory / 'independent-cleanup-verification.json')
        assert set(cleanup['terminated_instance_ids']) == ids
        assert set(cleanup['original_volume_ids']) == set(cloud['volume_ids'])
        for field in ('remaining_volumes', 'remaining_interfaces', 'remaining_security_groups',
                      'remaining_ssh_key_pairs', 'remaining_elastic_addresses'):
            assert cleanup[field] == []
        cleaned_at = read(directory / 'cleanup.json')['time']
        if previous_cleanup is not None:
            assert cloud['created_at'] > previous_cleanup
        previous_cleanup = cleaned_at
        observation = read(directory / 'observation-window-check-1.json') if number == 3 else None
        observed = {row['instance_id']: row for row in observation['rows']} if observation else {}
        for index, host in enumerate(hosts):
            key = read(directory / f'private-key-{index}.json')
            revoked = read(directory / f'key-revocation-{index}.json')['updateAPIKeyStatus']
            assert revoked['id'] == key['id'] and revoked['status'] == 'disabled'
            assert key['id'] not in keys
            keys.add(key['id'])
            native = (observed[host['id']]['native_goals'] if observation else
                      read(directory / host['id'] / 'var/lib/peer-operator/native-goals.json')['goals'])
            assert len(native) == 1 and native[0]['thread_id'] not in sessions
            sessions.add(native[0]['thread_id'])
        recording = read(directory / 'independent-recording-verification.json')
        assert recording['coverage_complete']
        assert recording['expected_objects'] == recording['stored_expected_objects']
        release = read(directory / 'release.json')
        row = {'repeat': number, 'subjects': 32, 'release': release,
               'cleanup_verified_at': cleaned_at, 'recording': recording}
        if number < 3:
            assert read(case / f'completed-repeat-{number}.json')['state'] == 'verified'
            assert read(directory / 'context-collection.json')['time'] >= release['T_start'] + 1800
            metrics = read(directory / 'metrics.json')
            scores = read(directory / 'independent-scores-verification.json')
            contacts = read(case / f'contacts-repeat-{number}.json')
            contact_summary = {key: contacts[key] for key in
                               ('repeat', 'T_start', 'deadline', 'attribution',
                                'timed_window_directed_peer_packet_pairs',
                                'timed_window_directed_peer_syn_pairs', 'cross_case_totals')}
            row.update({'collection_scope': 'full_30_minute_host_exports', 'scores': scores,
                        'requests': metrics['total_requests'], 'tokens': metrics['total_tokens'],
                        'provider': metrics['provider_observations'], 'quotas': metrics['quota_observations'],
                        'native_goal_states': dict(Counter(agent['goal_status'] for agent in metrics['agents'])),
                        'native_active_mean_seconds': sum(agent['native_goal_time_seconds'] for agent in metrics['agents']) / 32,
                        'process_start_skew_seconds': metrics['process_start_skew_seconds'],
                        'goal_acceptance_skew_seconds': metrics['goal_acceptance_skew_seconds'],
                        'resources': read(directory / 'independent-resources-verification.json'),
                        'contacts': contact_summary, 'cost': metrics['cost']})
            archives = [read(path) for path in (directory / 'archive-offload').glob('*.json')]
            exports = {entry['instance_id']: entry for entry in read(directory / 'export-manifest.json')}
            assert {entry['instance_id'] for entry in archives} == ids == set(exports)
            for archive in archives:
                assert archive['sha256'] == exports[archive['instance_id']]['archive_sha256']
                assert archive['remote_byte_readback_verified'] and archive['encryption'] == 'AES256'
                assert all(archive['public_access_block'].values())
            packets = read(directory / 'independent-packets-verification.json')
            assert {entry['instance_id'] for entry in packets} == ids
            row['original_archives'] = archives
            row['verified_packets'] = sum(entry['decoder_readback']['packets'] for entry in packets)
            shutil.copyfile(directory / 'independent-packets-verification.json', report / f'packets-repeat-{number}.json')
        else:
            gateways = [read(directory / f'gateway-{index}.json') for index in range(32)]
            requests = [edge['node'] for gateway in gateways for edge in gateway['requests']['edges']]
            executions = [edge['node'] for request in requests for edge in request['executions']['edges']]
            assert all(request['modelID'] == 'gpt-6.1-sol' for request in requests)
            assert all(execution['upstreamModelID'] == 'gpt-6.1-sol'
                       for execution in executions if execution['status'] == 'completed')
            usages = [edge['node'] for request in requests for edge in request['usageLogs']['edges']]
            hours = (cleaned_at - cloud['created_at']) / 3600 * 32
            row.update({'collection_scope': 'gateway_and_native_goal_observation',
                        'outcomes_unobserved': 32, 'observation_seconds_after_release': observation['time'] - release['T_start'],
                        'cleanup_verified_seconds_after_release': cleaned_at - release['T_start'],
                        'requests': len(requests), 'tokens': sum(usage['totalTokens'] for usage in usages),
                        'native_goal_states_at_observation': observation['goal_states'],
                        'provider': {'request_status_counts': dict(Counter(request['status'] for request in requests)),
                                     'execution_status_counts': dict(Counter(execution['status'] for execution in executions)),
                                     'execution_http_status_counts': dict(Counter(str(execution['responseStatusCode']) for execution in executions)),
                                     'reasoning_efforts': sorted({request['reasoningEffort'] for request in requests})},
                        'cost': {'instance_hours': hours,
                                 'ec2_ipv4_gp3_usd_estimate': hours * (0.0134 + 0.005 + 12 * 0.0952 / 730),
                                 'gateway_recorded_cost': sum(gateway['apiKeyQuotaUsages'][0]['usage']['totalCost'] for gateway in gateways),
                                 's3': read(directory / 'recording-receipts.json')['s3_standard_cost_estimate_usd']},
                        'original_archives': [], 'verified_packets': 0})
        manifest = read(case / f'publication-chunks-repeat-{number}.json')
        publication = read(case / f'publication-offload-repeat-{number}.json')
        combined = hashlib.sha256()
        for part in manifest['parts']:
            raw = (case / 'deliverables' / part['name']).read_bytes()
            assert len(raw) == part['bytes'] and hashlib.sha256(raw).hexdigest() == part['sha256']
            combined.update(raw)
        assert combined.hexdigest() == manifest['original_sha256'] == publication['sha256']
        assert publication['remote_byte_readback_verified'] and publication['server_validated_full_object_checksum']
        assert all(publication['public_access_block'].values())
        row['publication'] = manifest
        row['publication_offload'] = publication
        rows.append(row)
    assert len(instances) == len(volumes) == len(keys) == len(sessions) == 96
    diagnostics = []
    for number in (3, 2, 1):
        diagnostic = case / f'provider-admission-{number}'
        key = read(diagnostic / 'private-key-0.json')
        revoked = read(diagnostic / 'key-revocation-0.json')['updateAPIKeyStatus']
        assert revoked['id'] == key['id'] and revoked['status'] == 'disabled'
        provider = read(diagnostic / 'provider-admission.json')
        recording = read(diagnostic / 'recording-verification.json')
        assert recording['coverage_complete'] and recording['expected_objects'] == recording['stored_objects']
        diagnostics.append({'repeat': number, 'requests': provider['completed_requests'],
                            'tokens': sum(row['usage']['totalTokens'] for row in provider['quota_usage']),
                            'elapsed_seconds': provider['elapsed_seconds'], 'http_statuses': provider['http_statuses'],
                            'verified_objects': recording['stored_objects'], 'key_revoked': True})
    result = {'issue': 'SWH-105', 'case': 'N=32,K=2', 'launched_subjects': 96,
              'distinct_instances': 96, 'distinct_root_volumes': 96, 'distinct_sessions': 96,
              'revoked_subject_keys': 96, 'verified_cloud_cleanup_subjects': 96,
              'full_30_minute_repeats': 2, 'full_host_exports': 64, 'unobserved_subject_outcomes': 32,
              'confirmed_exact_count': sum(row.get('scores', {}).get('exact_count', 0) for row in rows),
              'case_mean_recall': None, 'requests': sum(row['requests'] for row in rows),
              'tokens': sum(row['tokens'] for row in rows),
              'expected_payload_objects': sum(row['recording']['expected_objects'] for row in rows),
              'verified_expected_payload_objects': sum(row['recording']['stored_expected_objects'] for row in rows),
              'retained_payload_objects': sum(row['recording']['verified_objects'] for row in rows),
              'original_archives': sum(len(row['original_archives']) for row in rows),
              'verified_packets': sum(row['verified_packets'] for row in rows),
              'infrastructure_usd_estimate': sum(row['cost']['ec2_ipv4_gp3_usd_estimate'] for row in rows),
              'gateway_recorded_cost': sum(row['cost']['gateway_recorded_cost'] for row in rows),
              'provider_diagnostics': diagnostics,
              'reservation': {'subjects': 32, 'state': 'held_pending_replacement_authorization'},
              'requested_action': 'Authorize 32 fresh replacement subjects, retaining all 128 launched subjects in reporting.',
              'repeats': list(reversed(rows))}
    result['confirmed_exact_fraction_lower_bound_all_launched'] = result['confirmed_exact_count'] / 96
    write(report / 'summary.json', result)
    write(report / 'case-verification.json', {key: value for key, value in result.items() if key != 'repeats'})
    write(report / 'observations.json', {'repeats': result['repeats']})
    write(report / 'artifacts.json', {'repeats': [{'repeat': row['repeat'],
          'collection_scope': row['collection_scope'], 'publication': row['publication'],
          'publication_offload': row['publication_offload'], 'original_archives': row['original_archives']} for row in reversed(rows)]})
    write(report / 'transport.json', {'repeats': [{'repeat': row['repeat'], **row['publication']} for row in reversed(rows)]})
    lines = ['# SWH-105: N=32, K=2', '',
             '| Repeat | Launched | Collected outcome scope | Mean recall | Exact | Requests | Tokens |',
             '| --- | ---: | --- | ---: | ---: | ---: | ---: |']
    for row in reversed(rows):
        scores = row.get('scores')
        recall = f"{scores['recall_mean']:.6%}" if scores else 'unobserved'
        exact = f"{scores['exact_count']}/32" if scores else 'unobserved'
        scope = '30-minute host collection' if scores else 'gateway and native-goal observation'
        lines.append(f"| {row['repeat']} | 32 | {scope} | {recall} | {exact} | {row['requests']} | {row['tokens']:,} |")
    lines += ['', f"All **96 launched subjects** remain in the case census. Full host collection covers 64 subjects; "
              f"32 third-repeat outcomes are unobserved. Confirmed exact submissions: {result['confirmed_exact_count']}/96 "
              f"({result['confirmed_exact_fraction_lower_bound_all_launched']:.4%} lower bound).", '',
              f"Repeat 3's native-goal observation covers all 32 sessions at {rows[2]['observation_seconds_after_release']:.3f} seconds "
              f"after release. Cloud cleanup was verified at {rows[2]['cleanup_verified_seconds_after_release']:.3f} seconds. "
              'The scheduled window was 1,800 seconds. The launch-check log records an SSH readback exit code of 1.', '',
              f"Gateway totals: **{result['requests']} requests**, **{result['tokens']:,} tokens**, "
              f"**{result['verified_expected_payload_objects']}/{result['expected_payload_objects']} expected payload objects**, "
              f"and **{result['retained_payload_objects']} retained objects**. "
              f"All 96 subject keys have revocation receipts and all 96 instances and original root volumes have verified cleanup.", '',
              f"Private encrypted S3 retains 64 original host archives and three scoped publications with complete byte readback. "
              f"Independent packet checks cover {result['verified_packets']:,} packets from the 64 collected captures.", '',
              f"Counted EC2, public IPv4 and gp3 estimate: ${result['infrastructure_usd_estimate']:.6f}. "
              f"Gateway recorded cost: {result['gateway_recorded_cost']}; subscription accounting fields remain in the evidence.", '',
              'The 32-place shared reservation remains held. Completing three full windows requires a fresh 32-subject '
              'replacement cohort and an actual total of 128 launched subjects. The replacement would use registered graph 3, '
              'fresh instances and keys, one native goal per instance, fresh admission checks and the same model and objective.', '']
    (report / 'README.md').write_text('\n'.join(lines))
    observations = ['# Native-goal and provider observations', '',
                    'Repeats 1 and 2 retain full host exports. Repeat 3 retains its timestamped native-goal observation and gateway exports.', '',
                    '| Repeat | Native state source | Native states | Exported execution HTTP fields |',
                    '| --- | --- | --- | --- |']
    for row in reversed(rows):
        states = row.get('native_goal_states', row.get('native_goal_states_at_observation'))
        source = 'host export' if row['repeat'] < 3 else '53-second observation'
        http = ', '.join(f"{'null' if code == 'None' else code}: {count}" for code, count in row['provider']['execution_http_status_counts'].items())
        observations.append(f"| {row['repeat']} | {source} | {json.dumps(states)} | {http} |")
    observations += ['', 'Per-repeat JSON retains actual gateway states, token usage, native activity, timing, resource observations, contacts and costs. '
                      'The third-repeat gateway export binds each request to the actual observed native-goal identity and records the observation SHA256.', '']
    (report / 'observations.md').write_text('\n'.join(observations))
    artifacts = ['# Evidence artifacts', '',
                 'Concatenate each publication’s parts in numeric order and verify its complete SHA256 before extraction. '
                 'Repeat 3 contains gateway records and native-goal observations. Repeats 1 and 2 contain full host exports.', '',
                 '| Repeat | Bytes | Parts | SHA256 |', '| --- | ---: | ---: | --- |']
    for row in reversed(rows):
        publication = row['publication']
        artifacts.append(f"| {row['repeat']} | {publication['original_bytes']} | {len(publication['parts'])} | `{publication['original_sha256']}` |")
    (report / 'artifacts.md').write_text('\n'.join(artifacts) + '\n')
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    source = case / 'deliverables/SWH-105-source.tar.gz'
    subprocess.run(['git', 'archive', '--format=tar.gz', '--output', str(source), revision,
                    'experiments/peer-discovery', 'experiments/peer-discovery-scheduling',
                    'README.md', 'AGENTS.md', '.cursor/rules/latest-first.mdc'], cwd=repository, check=True)
    write(report / 'source.json', {'revision': revision, 'archive': source.name,
                                 'bytes': source.stat().st_size, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    shutil.copyfile(case / 'publication-reverification-1.log', report / 'publication-reverification-1.txt')
    shutil.copyfile(case / 'publication-verification-3.log', report / 'publication-verification-3.txt')
    print(json.dumps({key: value for key, value in result.items() if key != 'repeats'}))


if __name__ == '__main__':
    main()
