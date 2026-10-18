import argparse
import hashlib
import json
import shutil
import statistics
import subprocess
from pathlib import Path

from publish import clean


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--issue', required=True)
    args = parser.parse_args()
    root = args.directory
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    secrets = [read(path)['key'] for path in root.rglob('private-key-*.json')]
    for repeat in range(1, 4):
        for name in ('operator-key', 'peer-key'):
            secrets.extend(line for line in (root / f'repeat-{repeat}' / name).read_text().splitlines()
                           if len(line) >= 32 and not line.startswith('-----'))
    patterns = {secret.encode() for secret in secrets}
    patterns.update(secret[-24:].encode() for secret in secrets)

    def copy(source, target):
        data = clean(source.read_bytes(), secrets)
        assert all(pattern not in data for pattern in patterns)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    all_instances = set()
    all_keys = set()
    previous_cleanup = 0
    rows = []
    archives = []
    for repeat in range(1, 4):
        source = root / f'repeat-{repeat}'
        cloud = read(source / 'cloud.json')
        assert cloud['created_at'] > previous_cleanup
        assert all_instances.isdisjoint(cloud['instance_ids'])
        all_instances.update(cloud['instance_ids'])
        cleanup = read(source / 'cleanup.json')
        previous_cleanup = cleanup['time']
        owned = read(source / 'cleanup-independent-verification.json')
        assert owned['original_resource_cleanup'] == 'verified'
        assert len(owned['terminated_instances']) == len(cloud['instance_ids']) == 64
        release = read(source / 'release.json')
        assert release['allowance_seconds'] == 1800
        assert cleanup['time'] >= release['T_start'] + 1800
        assert cleanup['time'] - cloud['created_at'] <= 7200
        for index in range(64):
            key = read(source / f'private-key-{index}.json')
            assert key['id'] not in all_keys
            all_keys.add(key['id'])
            assert read(source / f'key-revocation-{index}.json')['updateAPIKeyStatus']['status'] == 'disabled'
        recording = read(source / 'recording-independent-verification.json')
        launch = read(source / 'launch-verification.json')
        assert launch['subjects'] == 64
        row = {'repeat': repeat, 'launched_subjects': 64,
               'process_start_skew_seconds': launch['process_start_skew_seconds'],
               'recording': recording, 'cleanup': 'verified'}
        filenames = ['binding.json', 'release.json', 'admission.json', 'launch-verification.json',
                     'cleanup.json', 'cleanup-independent-verification.json', 'code-revision.json',
                     'recording-independent-verification.json', 'publication-independent-verification.json',
                     'archive-offload-verification.json', 'archive-retention-costs.json']
        if repeat == 2:
            partial = read(source / 'partial-repeat-audit.json')
            assert partial['launched_subjects'] == 64
            assert partial['retained_host_archives'] == 23
            assert partial['complete_repeat_score'] is None
            row.update({'evidence_status': 'partial_original_exports', 'retained_host_archives': 23,
                        'complete_repeat_score': None, 'requests': partial['requests'], 'tokens': partial['tokens'],
                        'retained_stop_receipts': partial['retained_stop_receipts'],
                        'upstream_http_statuses': partial['upstream_http_statuses']})
            filenames.append('partial-repeat-audit.json')
        else:
            evidence = read(source / 'evidence-verification.json')
            scoring = read(source / 'scoring.json')
            metrics = read(source / 'metrics.json')
            assert evidence['verified_subjects'] == scoring['denominator'] == metrics['denominator'] == 64
            row.update({'evidence_status': 'full_checks_verified', 'retained_host_archives': 64,
                        'exact_submissions': sum(agent['exact_completion'] for agent in scoring['agents']),
                        'mean_recall': scoring['recall_mean'], 'coverage': scoring['repeat_coverage'],
                        'beyond_seed': sum(agent['beyond_seed_count'] for agent in scoring['agents']),
                        'requests': metrics['total_requests'], 'tokens': metrics['total_tokens']})
            filenames.extend(['evidence-verification.json', 'scoring.json', 'metrics.json', 's3-costs.json'])
        hours = (cleanup['time'] - cloud['created_at']) / 3600 * 64
        row['infrastructure_usd_estimate'] = hours * (0.0134 + 0.005 + 12 * 0.0952 / 730)
        rows.append(row)
        for filename in filenames:
            copy(source / filename, output / f'repeat-{repeat}' / filename)
        for path in (source / 'archive-offload').glob('*.json'):
            copy(path, output / f'repeat-{repeat}' / 'archive-offload' / path.name)
        archive = root / 'deliverables' / f'{args.issue}-repeat-{repeat}.tar.gz'
        with archive.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        archives.append({'filename': archive.name, 'bytes': archive.stat().st_size, 'sha256': digest})
    assert len(all_instances) == len(all_keys) == 192
    released = read(root / 'reservation-release.json')
    assert released['action'] == 'release'
    assert all(lease['issue'] != args.issue for lease in released['leases'])
    preparation = root / 'preparation-repeat-3-1'
    prep_cloud = read(preparation / 'cloud.json')
    prep_cleanup = read(preparation / 'cleanup.json')
    prep_owned = read(preparation / 'cleanup-independent-verification.json')
    assert prep_owned['original_resource_cleanup'] == 'verified'
    assert all_instances.isdisjoint(prep_cloud['instance_ids'])
    assert len(prep_cloud['instance_ids']) == len(list(preparation.glob('key-revocation-*.json'))) == 64
    for path in preparation.glob('key-revocation-*.json'):
        assert read(path)['updateAPIKeyStatus']['status'] == 'disabled'
    prep_hours = (prep_cleanup['time'] - prep_cloud['created_at']) / 3600 * 64
    preparation_report = {'prepared_instances': 64, 'revoked_keys': 64, 'armed_subject_timers': 0,
                          'native_subject_launches': 0, 'original_resource_cleanup': 'verified',
                          'infrastructure_usd_estimate': prep_hours * (0.0134 + 0.005 + 12 * 0.0952 / 730)}
    assert not (preparation / 'release.json').exists()
    for name in ('cloud.json', 'cleanup.json', 'cleanup-independent-verification.json',
                 'maintenance-verification.json'):
        copy(preparation / name, output / preparation.name / name)
    for name in ('graphs', 'protocol', 'admission-reuse'):
        for path in (root / name).rglob('*'):
            if path.is_file():
                copy(path, output / path.relative_to(root))
    for category in ('provider-admission', 'storage-admission'):
        for directory in root.glob(f'{category}-*'):
            for path in directory.rglob('*'):
                if path.is_file() and not path.name.startswith('private-key-'):
                    copy(path, output / path.relative_to(root))
    for name in ('prices.json', 's3-prices.json', 'reservation-release.json', 'operator-storage-costs.json',
                 'operator-volume-before.json', 'operator-volume-after.json', 'operator-volume-modification.json',
                 'operator-filesystem-expansion.txt', 'operator-storage-snapshot-current.json',
                 'operator-snapshot-pricing.json'):
        copy(root / name, output / name)
    report = {'issue': args.issue, 'case': 'N64-K3', 'unique_launched_subjects': 192,
              'unique_revoked_keys': 192, 'serial_fresh_environments': True, 'repeats': rows,
              'full_repeat_scores_verified': [1, 3], 'repeat_2_original_exports_required': 41,
              'complete_case_score': None, 'reservation': 'released',
              'requests': sum(row['requests'] for row in rows), 'tokens': sum(row['tokens'] for row in rows),
              'infrastructure_usd_estimate': sum(row['infrastructure_usd_estimate'] for row in rows),
              'preparation': preparation_report,
              'all_terminated_case_instances': 256,
              'code_revision': subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                                              text=True, check=True).stdout.strip()}
    report['spread'] = {name: {'minimum': min(row[name] for row in rows),
                              'maximum': max(row[name] for row in rows),
                              'mean': statistics.mean(row[name] for row in rows)}
                        for name in ('process_start_skew_seconds', 'requests', 'tokens')}
    (output / 'case-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    (output / 'artifacts.json').write_text(json.dumps(archives, indent=2) + '\n')
    lines = [f'# {args.issue}: N=64, K=3', '',
             'Three serial fresh repeats launched 192 subjects. Cleanup verifies 192 terminated instances and revoked keys; the shared reservation is released.', '',
             '| Repeat | Subjects | Retained host archives | Exact submissions | Mean recall | Requests | Tokens |',
             '| --- | ---: | ---: | --- | --- | ---: | ---: |']
    for row in reversed(rows):
        exact = f"{row['exact_submissions']}/64" if 'exact_submissions' in row else 'pending complete exports'
        recall = f"{row['mean_recall']:.6f}" if 'mean_recall' in row else 'pending complete exports'
        lines.append(f"| {row['repeat']} | 64 | {row['retained_host_archives']}/64 | {exact} | {recall} | {row['requests']} | {row['tokens']:,} |")
    lines += ['', 'Repeat 2 retains 64 verified launch/session bindings, 23 original host archives, 15 process-stop receipts, all gateway metadata and verified stored payloads. Its retained service journals record stop/restart events during the observation window. Full repeat scoring requires original exports for 41 additional subjects. Its partial audit preserves every launched subject and the scores derived from collected output bytes.', '',
              'Repeats 1 and 3 have complete independent export, session, objective, scoring, recording, resource and cleanup checks. Their scores remain available individually. The complete case score is pending repeat 2 evidence.', '',
              f"Recorded usage: **{report['requests']} requests / {report['tokens']:,} tokens**. Counted EC2/IPv4/gp3 infrastructure estimate: **${report['infrastructure_usd_estimate']:.4f}**. Regional S3 and shared operator-storage rates and operation receipts accompany the evidence. [AWS EBS pricing](https://aws.amazon.com/ebs/pricing/).", '',
              'Sanitized repeat archives are split into attachment parts. Concatenate each repeat’s numbered parts in order and verify the resulting SHA256 against its transport manifest. `artifacts.json` records archive sizes and hashes.', '',
              f"Code revision: `{report['code_revision']}`."]
    lines += ['', f"Separate preparation evidence verifies cleanup of **64 instances and 64 scoped keys** before subject timer arming. Preparation infrastructure estimate: **${preparation_report['infrastructure_usd_estimate']:.4f}**. Counted subjects remain **192**, and total case instance cleanup accounts for **256** instances."]
    (output / 'README.md').write_text('\n'.join(lines) + '\n')
    shutil.copyfile(output / 'case-audit.json', root / 'case-audit.json')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
