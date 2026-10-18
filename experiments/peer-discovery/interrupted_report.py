import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re

from publish import clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory
    binding = json.loads((directory / 'binding.json').read_text())
    cloud = json.loads((directory / 'cloud.json').read_text())
    cleanup = json.loads((directory / 'cleanup.json').read_text())
    recording = json.loads((directory / 'independent-recording-verification.json').read_text())
    receipts = json.loads((directory / 'recording-receipts.json').read_text())
    secrets = [json.loads(path.read_text())['key'] for path in directory.glob('private-key-*.json')]
    credentials = re.compile(b'|'.join(re.escape(secret.encode()) for secret in secrets))
    rows = []
    calls = {}
    for index, host in enumerate(binding['hosts']):
        key = json.loads((directory / f'private-key-{index}.json').read_text())
        revocation = json.loads((directory / f'key-revocation-{index}.json').read_text())['updateAPIKeyStatus']
        assert revocation['id'] == key['id'] and revocation['status'] == 'disabled'
        gateway = json.loads((directory / f'gateway-{index}.json').read_text())
        requests = [edge['node'] for edge in gateway['requests']['edges']]
        executions = [edge['node'] for request in requests for edge in request['executions']['edges']]
        usages = [edge['node'] for request in requests for edge in request['usageLogs']['edges']]
        launch_path = directory / f'{host["id"]}-launch-verification.json'
        launch = json.loads(launch_path.read_text()) if launch_path.exists() else None
        session = recording['provider_session_bindings'].get(host['id'])
        if launch:
            assert launch['markers'] == [host['id']]
            assert launch['native-goals']['goals'][0]['thread_id'] == session
        rows.append({'instance_id': host['id'], 'public_ip': host['public_ip'],
                     'api_key_id': key['id'], 'key_status': revocation['status'],
                     'process_native_goal_receipt': bool(launch), 'provider_session_id': session,
                     'requests': len(requests),
                     'tokens': sum(usage['totalTokens'] for usage in usages),
                     'request_states': dict(Counter(request['status'] for request in requests)),
                     'execution_http_statuses': dict(Counter(str(node['responseStatusCode']) for node in executions)),
                     'quota_usage': gateway['apiKeyQuotaUsages']})
    for receipt in receipts['receipts']:
        name = receipt['object_key']
        if '/executions/' in name or not name.endswith(('/request_body.json', '/response_body.json')):
            continue
        path = directory / 'stored-payloads' / (name + '.gz')
        raw = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(raw).hexdigest() == receipt['sha256']
        payload = json.loads(clean(raw, credentials))
        events = payload['input'] if name.endswith('/request_body.json') else payload.get('output', [])
        for event in events:
            if event.get('type') in ('custom_tool_call', 'function_call'):
                call_id = event['call_id']
                identity = (receipt['instance_id'], call_id)
                detail = {'instance_id': receipt['instance_id'], 'call_id': call_id,
                          'name': event['name'], 'type': event['type'],
                          'input': event.get('input', event.get('arguments'))}
                if identity in calls:
                    assert calls[identity]['tool'] == detail
                else:
                    calls[identity] = {'tool': detail, 'source_object': name,
                                       'source_object_sha256': receipt['sha256']}
    count = len(binding['hosts'])
    assert count == len(cloud['instance_ids']) == len(secrets)
    assert recording['subjects'] == count
    assert sum(row['requests'] for row in rows) == recording['requests']
    hours = (cleanup['time'] - cloud['created_at']) / 3600 * count
    http = Counter()
    for row in rows:
        http.update(row['execution_http_statuses'])
    release = json.loads((directory / 'release-verification.json').read_text())
    report = {'issue': cloud['issue'], 'repeat': binding['repeat'],
              'state': 'awaiting_protocol_decision', 'provisioned_subjects': count,
              'released_subjects': release['subjects'], 'retained_subject_denominator': count,
              'process_native_goal_receipts': sum(row['process_native_goal_receipt'] for row in rows),
              'provider_session_subjects': sum(row['provider_session_id'] is not None for row in rows),
              'host_archive_exports': len(list(directory.glob('*-raw.tar.gz'))),
              'completed_repeat_windows': 0, 'independently_scored_subjects': 0,
              'recall': None, 'precision': None, 'exact_completion': None,
              'scheduled_start_utc': release['start_utc'], 'scheduled_deadline_utc': release['deadline_utc'],
              'termination_requested_at': json.loads((directory / 'termination.json').read_text())['TerminatingInstances'],
              'cleanup_completed_at_epoch': cleanup['time'], 'revoked_keys': count,
              'requests': recording['requests'], 'tokens': sum(row['tokens'] for row in rows),
              'execution_http_statuses': dict(http), 'recording': recording,
              'instance_hours': hours,
              'infrastructure_usd_estimate': hours * (0.0134 + 0.005 + 12 * 0.0952 / 730),
              's3_cost_estimate_usd': receipts['s3_standard_cost_estimate_usd'],
              'tool_calls': len(calls), 'subjects_with_tool_calls': len({key[0] for key in calls}),
              'subjects': rows}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'interrupted-repeat.json').write_text(json.dumps(report, indent=2) + '\n')
    (args.output / 'provider-tool-calls.json').write_text(json.dumps(list(calls.values()), indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('subjects', 'recording', 'termination_requested_at')}, indent=2))


if __name__ == '__main__':
    main()
