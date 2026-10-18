import argparse
import json
import subprocess
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--issue-id', required=True)
    parser.add_argument('--issue-key', required=True)
    parser.add_argument('--comment-file', type=Path, required=True)
    parser.add_argument('--report', type=Path, action='append', required=True)
    parser.add_argument('--case-audit', action='store_true')
    args = parser.parse_args()
    if args.case_audit:
        case = read(args.directory / 'case-audit.json')
        assert case['serial_fresh_environments']
        assert case['unique_launched_subjects'] == case['unique_revoked_keys'] == 192
        assert case['complete_case_score'] is None
        assert case['repeat_2_original_exports_required'] == 41
        assert all(row['cleanup'] == 'verified' for row in case['repeats'])
    else:
        case = read(args.directory / 'case-verification.json')
        assert case['serial_fresh_environments']
        assert case['unique_instances'] == case['unique_revoked_keys'] == sum(row['subjects'] for row in case['repeats'])
    release = read(args.directory / 'reservation-release.json')
    assert release['action'] == 'release'
    assert all(lease['issue'] != args.issue_key for lease in release['leases'])
    files = []
    manifests = sorted((args.directory / 'transport').glob('*.transport.json'))
    assert len(manifests) == 3
    for path in manifests:
        receipt = read(path)
        assert receipt['combined_part_readback_verified']
        assert sum(row['bytes'] for row in receipt['parts']) == receipt['bytes']
        for row in receipt['parts']:
            part = path.parent / row['name']
            assert part.stat().st_size == row['bytes']
            files.append(part)
        files.append(path)
    files.extend(args.report)
    assert len(files) == len(set(files)) and all(path.is_file() for path in files)
    command = ['multica', 'issue', 'comment', 'add', args.issue_id,
               '--content-file', str(args.comment_file), '--output', 'table']
    for path in files:
        command.extend(['--attachment', str(path)])
    result = subprocess.run(command, capture_output=True, text=True)
    receipt = {'issue_id': args.issue_id, 'attachments': [path.name for path in files],
               'stdout': result.stdout, 'stderr': result.stderr, 'exit_code': result.returncode}
    (args.directory / 'delivery-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    result.check_returncode()
    print(result.stdout, end='')
    print(json.dumps({'comment_posted': True, 'attachments': len(files)}))


if __name__ == '__main__':
    main()
