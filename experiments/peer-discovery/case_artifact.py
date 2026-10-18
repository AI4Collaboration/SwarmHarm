import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

from publish import clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    secrets = [json.loads(path.read_text())['key']
               for path in args.directory.glob('repeat-*/private-key-*.json')]
    expected_subjects = sum(len(json.loads((args.directory / f'repeat-{number}' / 'binding.json').read_text())['hosts'])
                            for number in (1, 2, 3))
    assert expected_subjects > 0
    assert len(secrets) == len(set(secrets)) == expected_subjects
    secrets.extend(json.loads(path.read_text())['key']
                   for path in args.directory.glob('provider-admission-*/private-key-*.json'))
    credentials = re.compile(b'|'.join(re.escape(secret.encode()) for secret in secrets))
    selected = {}

    def include(path, name):
        assert name not in selected
        raw = path.read_bytes()
        selected[name] = (gzip.compress(clean(gzip.decompress(raw), credentials), mtime=0)
                          if name.endswith('.json.gz') else clean(raw, credentials))

    for path in args.report.rglob('*'):
        if path.is_file():
            include(path, 'report/' + str(path.relative_to(args.report)))
    for path in args.directory.glob('*.json'):
        include(path, 'admission/' + path.name)
    for path in (args.directory / 'protocol').rglob('*'):
        if path.is_file():
            include(path, 'protocol/' + str(path.relative_to(args.directory / 'protocol')))
    for diagnostic in args.directory.glob('provider-admission-*'):
        for path in diagnostic.rglob('*'):
            if path.is_file() and path.suffix in ('.json', '.gz', '.txt') and not path.name.startswith('private-key-'):
                include(path, str(path.relative_to(args.directory)))
    names = ('release.json', 'release-verification.json', 'launch-verification.json',
             'evidence-verification.json', 'independent-cleanup-verification.json', 'cleanup.json',
             'independent-recording-verification.json', 'publication-verification.json',
             'scoring.json', 'metrics.json', 'cloud.json', 'binding.json', 'recording-receipts.json',
             'independent-scores-verification.json', 'independent-resources-verification.json',
             'recording-policy-release.json', 'shared-admission.json', 'finalization.json',
             'export-manifest.json')
    for repeat in (3, 2, 1):
        directory = args.directory / f'repeat-{repeat}'
        for name in names:
            include(directory / name, f'repeat-{repeat}/' + name)
        for path in directory.glob('observation-*.json'):
            include(path, f'repeat-{repeat}/' + path.name)
        for path in directory.glob('*-compaction.json'):
            include(path, f'repeat-{repeat}/' + path.name)
        for path in (directory / 'archive-offload').glob('*.json'):
            include(path, f'repeat-{repeat}/archive-offload/' + path.name)
    manifest = {name: {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                for name, raw in sorted(selected.items())}
    selected['case-manifest.json'] = json.dumps(manifest, indent=2).encode()
    with tarfile.open(args.output, 'w:gz') as archive:
        for name, raw in sorted(selected.items()):
            assert credentials.search(raw) is None
            if name.endswith('.json'):
                json.loads(raw)
            if name.endswith('.json.gz'):
                json.loads(gzip.decompress(raw))
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(raw))
    with tarfile.open(args.output) as archive:
        assert set(archive.getnames()) == set(selected)
        for name, expected in manifest.items():
            raw = archive.extractfile(name).read()
            assert len(raw) == expected['size'] and hashlib.sha256(raw).hexdigest() == expected['sha256']
    print(json.dumps({'files': len(selected), 'bytes': args.output.stat().st_size,
                      'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
