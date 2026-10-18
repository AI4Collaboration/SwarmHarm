import argparse
import collections
import hashlib
import json
import tarfile
from pathlib import Path

from grade import grade


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory
    binding = read(directory / 'binding.json')
    launch = read(directory / 'launch-verification.json')
    cleanup = read(directory / 'cleanup-independent-verification.json')
    recording = read(directory / 'recording-independent-verification.json')
    assert launch['subjects'] == len(binding['hosts'])
    assert cleanup['original_resource_cleanup'] == 'verified'
    addresses = [host['public_ip'] for host in binding['hosts']]
    rows = []
    for index, host in enumerate(binding['hosts']):
        archive = directory / f'{host["id"]}-raw.tar.gz'
        revoked = read(directory / f'key-revocation-{index}.json')
        assert revoked['updateAPIKeyStatus']['status'] == 'disabled'
        row = {'instance_id': host['id'], 'archive_retained': archive.is_file(),
               'collected_output_score': None, 'stop_receipt_retained': False}
        if archive.is_file():
            with archive.open('rb') as stream:
                row['archive_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
            row['archive_bytes'] = archive.stat().st_size
            with tarfile.open(archive) as bundle:
                members = {member.name: member for member in bundle if member.isfile()}
                prefix = 'var/lib/peer-operator/'
                receipt = json.loads(bundle.extractfile(members[prefix + 'collection-receipt.json']).read())
                row['collection_time_ns'] = receipt['time_ns']
                row['stop_receipt_retained'] = prefix + 'process-stop.json' in members
                if row['stop_receipt_retained']:
                    row['stop_receipt'] = json.loads(bundle.extractfile(members[prefix + 'process-stop.json']).read())
                output_name = 'home/agent/discovered_peers.json'
                raw = None
                if output_name in members:
                    raw = bundle.extractfile(members[output_name]).read()
                    recorded = receipt['files']['/' + output_name]
                    assert hashlib.sha256(raw).hexdigest() == recorded['sha256']
                row['collected_output_score'] = grade(raw, host['public_ip'], addresses, host['seeds'])
        rows.append(row)
    metadata = [read(directory / f'gateway-{index}.json') for index in range(len(rows))]
    requests = [edge['node'] for item in metadata for edge in item['requests']['edges']]
    usages = [edge['node'] for request in requests for edge in request['usageLogs']['edges']]
    statuses = collections.Counter(str(edge['node']['responseStatusCode'])
                                   for request in requests for edge in request['executions']['edges'])
    report = {'repeat': binding['repeat'], 'launched_subjects': len(rows),
              'retained_host_archives': sum(row['archive_retained'] for row in rows),
              'retained_stop_receipts': sum(row['stop_receipt_retained'] for row in rows),
              'subjects_requiring_original_exports': [row['instance_id'] for row in rows if not row['archive_retained']],
              'complete_repeat_score': None, 'requests': len(requests),
              'tokens': sum(usage['totalTokens'] for usage in usages),
              'upstream_http_statuses': dict(statuses), 'recording': recording,
              'launch': {key: value for key, value in launch.items() if key != 'native_goal_launches'},
              'revoked_keys': len(rows), 'terminated_instances': len(cleanup['terminated_instances']),
              'observations': 'Collected output scores apply to retained host archives; complete repeat grading requires every original export.',
              'subjects': rows}
    (directory / 'partial-repeat-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('subjects', 'subjects_requiring_original_exports')}))


if __name__ == '__main__':
    main()
