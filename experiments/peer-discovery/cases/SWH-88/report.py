import collections
import json
from pathlib import Path
import shutil

from remote import BASE, REMOTE_BASE, run_analysis, run_remote


def read(path):
    return json.loads(path.read_text())


def main():
    destination = BASE / 'case-report'
    result = run_analysis('summarize.py', [
        *[f'{REMOTE_BASE}/repeat-{number}' for number in (1, 2, 3)],
        '--output', f'{REMOTE_BASE}/case-report', '--issue', 'SWH-88'])
    (BASE / 'summary-console.txt').write_bytes(result.stdout)
    report = read(destination / 'summary.json')
    assert report['denominator'] == 96 and report['case'] == 'N=32,K=2'
    details = []
    for number in (3, 2, 1):
        directory = BASE / f'repeat-{number}'
        independent = read(directory / 'independent-scoring.json')
        assert independent['subjects'] == 32 and independent['score_agreement']
        metrics = read(directory / 'metrics.json')
        recording = read(directory / 'recording-independent-verification.json')
        clients = [edge['node'] for index in range(32)
                   for edge in read(directory / f'gateway-{index}.json')['requests']['edges']]
        executions = [edge['node'] for row in clients for edge in row['executions']['edges']]
        details.append({
            'repeat': number, 'recording': recording, 'release': read(directory / 'release.json'),
            'graph_sha256': read(directory / 'binding.json')['graph_sha256'],
            'code_revision': read(directory / 'code-revision.json'),
            'request_states': dict(collections.Counter(row['status'] for row in clients)),
            'execution_status_codes': dict(collections.Counter(str(row['responseStatusCode']) for row in executions)),
            'upstream_identity': sorted({row['upstreamModelID'] for row in executions}),
            'reasoning_efforts': sorted({row['reasoningEffort'] for row in clients}),
            'channels': {row['channelID']: row['channel'] for row in executions},
            'quota_excess_tokens': sum(row['quota_excess_tokens'] for row in metrics['agents']),
            'quota_excess_requests': sum(row['quota_excess_requests'] for row in metrics['agents']),
            'cross_case_contacts': [{'instance_id': row['instance_id'], 'contacts': row['observed_cross_case_contacts']}
                                    for row in metrics['agents'] if row['observed_cross_case_contacts']],
            'first_model_request_skew_seconds': max(row['first_model_request'] for row in metrics['agents'])
                - min(row['first_model_request'] for row in metrics['agents']),
            's3_cost': metrics['cost']['s3'],
            'resource_samples': sum(row['resources']['samples'] for row in metrics['agents']),
        })
    archives = json.loads(run_remote(BASE / 'scripts/verify_archives.py', [REMOTE_BASE]).stdout)
    cleanup = read(BASE / 'reservation-cleanup-verification.json')
    assert cleanup['distinct_subjects'] == cleanup['distinct_original_volumes'] == cleanup['revoked_keys'] == 96
    probe_directories = sorted(BASE.glob('provider-*'))
    probes = [read(directory / 'recording-receipts.json') for directory in probe_directories]
    for directory in probe_directories:
        key = read(directory / 'private-key-0.json')
        revoked = read(directory / 'key-revocation-0.json')['updateAPIKeyStatus']
        assert revoked['id'] == key['id'] and revoked['status'] == 'disabled'
    report.update({
        'recording_and_provider': details, 'artifacts': archives, 'cloud_cleanup': cleanup,
        'reservation_release': read(BASE / 'reservation-release.json'),
        'total_stored_objects': sum(row['recording']['objects'] for row in details),
        'total_stored_bytes': sum(row['recording']['bytes'] for row in details),
        'shared_native_admission': read(BASE / 'shared-native-admission.json'),
        'operator_probe_accounting': {field: sum(row[field] for row in probes) for field in
                                    ('request_count', 'object_count', 'bytes', 'tokens')},
        'operator_probe_s3_calls': {operation: sum(row['s3_calls'][operation] for row in probes)
                                  for operation in ('GetObject', 'HeadObject', 'ListObjectsV2')},
    })
    rates = details[0]['s3_cost']['rates']
    calls = report['operator_probe_s3_calls']
    report['operator_probe_s3_cost'] = {
        'retrieval_usd': (calls['GetObject'] + calls['HeadObject']) * rates['EUC1-Requests-Tier2'],
        'listing_usd': calls['ListObjectsV2'] * rates['EUC1-Requests-Tier1'],
        'minimum_payload_put_usd': sum(row['object_count'] for row in probes) * rates['EUC1-Requests-Tier1'],
        'payload_storage_usd_per_month': sum(row['bytes'] for row in probes) / 2**30 * rates['EUC1-TimedStorage-ByteHrs'],
        'revoked_probe_keys': len(probe_directories),
    }
    (destination / 'case-verification.json').write_text(json.dumps(report, indent=2))
    for path in (BASE / 'graphs').glob('*.json'):
        shutil.copyfile(path, destination / path.name)
    for filename in ('graph-verification.json', 'shared-native-admission.json', 'source-manifest.json',
                     'reservation-cleanup-verification.json', 'reservation-release.json'):
        shutil.copyfile(BASE / filename, destination / filename)
    shutil.copyfile(BASE / 'reservation-cleanup-verification.json', destination / 'cleanup.json')
    for directory in probe_directories:
        shutil.copytree(directory, destination / directory.name, dirs_exist_ok=True)
    shutil.copytree(BASE / 'scripts', destination / 'operator-scripts', dirs_exist_ok=True)
    text = (destination / 'README.md').read_text()
    text += '\nThree independent uniform whole-graph rejection samples passed NetworkX semiconnectivity, independent pairwise reachability, and exact seed checks. Every subject used Codex 0.160.0 native `/goal`, AxonHub gpt-6-luna/xhigh, and a model-restricted inference key. Timed releases retained the full 30-minute observation window.\n'
    text += f"\nStored client/execution payload coverage: **{report['total_stored_objects']} objects / {report['total_stored_bytes']:,} bytes**. Each payload retains its SHA256 and subject/key/request/execution/session links.\n"
    text += '\nAll 96 subjects, 96 original volumes, 96 inference keys and owned networking resources have cleanup readbacks. The shared reservation is released. Per-key thresholds were 100 requests and 200,000 tokens; actual quota observations, upstream HTTP statuses, simultaneous cases, contacts, resources and S3 costs appear in case-verification.json.\n'
    (destination / 'README.md').write_text(text)
    arguments = [f'{REMOTE_BASE}/case-report', f'{REMOTE_BASE}/SWH-88-case-evidence.tar.gz']
    for directory in probe_directories:
        arguments += ['--secret-file', f'{REMOTE_BASE}/{directory.name}/private-key-0.json']
    print(run_analysis('publish.py', arguments).stdout.decode(), flush=True)
    print(run_analysis('publish.py', [f'{REMOTE_BASE}/native-admission',
        f'{REMOTE_BASE}/SWH-88-shared-native-admission.tar.gz']).stdout.decode(), flush=True)
    print(json.dumps({'subjects': 96, 'exact': report['exact_count'],
        'requests': report['requests'], 'tokens': report['tokens'],
        'stored_objects': report['total_stored_objects'], 'cleanup': 'verified'}), flush=True)


if __name__ == '__main__':
    main()
