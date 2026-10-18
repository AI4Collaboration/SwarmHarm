import argparse
import hashlib
import json
import shutil
from pathlib import Path

from publish import clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--issue', required=True)
    args = parser.parse_args()
    verification = json.loads((args.directory / 'case-verification.json').read_text())
    assert verification['unique_instances'] == verification['unique_revoked_keys']
    assert verification['unique_instances'] == sum(row['subjects'] for row in verification['repeats'])
    args.output.mkdir(parents=True, exist_ok=True)
    for filename in ('case-verification.json', 'reservation-release.json', 'prices.json', 's3-prices.json'):
        shutil.copyfile(args.directory / filename, args.output / filename)
    storage = args.output / 'operator-storage'
    storage.mkdir(exist_ok=True)
    for filename in ('operator-volume-before.json', 'operator-volume-modification.json',
                     'operator-volume-after.json', 'operator-filesystem-expansion.txt',
                     'operator-storage-snapshot.json', 'operator-storage-costs.json',
                     'operator-snapshot-pricing.json', 'operator-storage-snapshot-current.json'):
        path = args.directory / filename
        if path.is_file():
            shutil.copyfile(path, storage / path.name)
    shutil.copytree(args.directory / 'graphs', args.output / 'graphs', dirs_exist_ok=True)
    shutil.copytree(args.directory / 'protocol', args.output / 'protocol', dirs_exist_ok=True)
    shutil.copytree(args.directory / 'admission-reuse', args.output / 'admission-reuse', dirs_exist_ok=True)
    diagnostic_keys = [json.loads(path.read_text())['key'] for path in
                       args.directory.glob('provider-admission-*/private-key-0.json')]
    for repeat in range(1, 4):
        for category in ('provider-admission', 'storage-admission'):
            source = args.directory / f'{category}-{repeat}'
            target = args.output / source.name
            for path in source.rglob('*'):
                if path.is_file() and path.name != 'private-key-0.json':
                    destination = target / path.relative_to(source)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    data = clean(path.read_bytes(), diagnostic_keys)
                    assert all(key.encode() not in data for key in diagnostic_keys)
                    destination.write_bytes(data)
    artifacts = []
    for repeat in range(1, 4):
        source = args.directory / f'repeat-{repeat}'
        output = args.output / f'repeat-{repeat}'
        output.mkdir(exist_ok=True)
        offload = source / 'archive-offload-verification.json'
        if offload.is_file():
            shutil.copyfile(offload, output / offload.name)
            shutil.copyfile(source / 'archive-retention-costs.json', output / 'archive-retention-costs.json')
            shutil.copytree(source / 'archive-offload', output / 'archive-offload', dirs_exist_ok=True)
        for filename in ('scoring.json', 'scoring-independent-verification.json', 'evidence-verification.json', 'recording-independent-verification.json',
                         'launch-verification.json',
                         'cleanup-independent-verification.json', 'traffic-analysis-verification.json',
                         'publication-independent-verification.json',
                         's3-costs.json', 'code-revision.json', 'analysis-revision.json', 'release.json', 'admission.json'):
            shutil.copyfile(source / filename, output / filename)
        cleanup = json.loads((source / 'cleanup.json').read_text())
        instances = [instance for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances']]
        assert all(instance['State']['Name'] == 'terminated' for instance in instances)
        summary = {'time': cleanup['time'], 'terminated_instances': [instance['InstanceId'] for instance in instances],
                   'revoked_inference_keys': len(list(source.glob('key-revocation-*.json'))),
                   **{name: cleanup[name] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs')}}
        (output / 'cleanup-summary.json').write_text(json.dumps(summary, indent=2))
        release = json.loads((source / 'release-verification.json').read_text())
        (output / 'release-verification.json').write_text(json.dumps(
            {name: value for name, value in release.items() if name not in ('instances', 'volumes')}, indent=2))
        archive = args.directory / 'deliverables' / f'{args.issue}-repeat-{repeat}.tar.gz'
        with archive.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        artifacts.append({'filename': archive.name, 'bytes': archive.stat().st_size,
                          'sha256': digest})
    (args.output / 'artifacts.json').write_text(json.dumps(artifacts, indent=2))
    print(json.dumps({'subjects': verification['unique_instances'], 'repeat_artifacts': artifacts}, indent=2))


if __name__ == '__main__':
    main()
