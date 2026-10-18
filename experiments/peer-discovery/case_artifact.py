import argparse
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

from publish import clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directories', type=Path, nargs=3)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--admission', type=Path, required=True)
    parser.add_argument('--audits', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    secrets = [json.loads(path.read_text())['key'] for directory in args.directories
               for path in directory.glob('private-key-*.json')]
    expected = sum(len(json.loads((directory / 'binding.json').read_text())['hosts'])
                   for directory in args.directories)
    assert len(secrets) == len(set(secrets)) == expected
    credentials = re.compile(b'|'.join(re.escape(secret.encode()) for secret in secrets))
    selected = {}
    def include(path, name):
        assert name not in selected
        selected[name] = clean(path.read_bytes(), credentials)
    for path in args.report.rglob('*'):
        if path.is_file():
            include(path, 'report/' + str(path.relative_to(args.report)))
    admission_names = ('graph-1.json', 'graph-2.json', 'graph-3.json', 'operator-admission.json',
                       'shared-price-receipt.json', 'recording-policy-admission.json',
                       'admission-initial.json', 'admission-before-repeat-3.json', 'reservation-release.json')
    for name in admission_names:
        path = args.admission / name
        include(path, 'admission/' + path.name)
    for path in args.audits.rglob('*'):
        if path.is_file() and path.suffix in ('.json', '.jsonl'):
            include(path, 'audits/' + str(path.relative_to(args.audits)))
    required = ('release-verification.json', 'launch-verification.json', 'evidence-verification.json',
                'cleanup.json', 'independent-cleanup-verification.json',
                'independent-recording-verification.json', 'publication-verification.json',
                'scoring.json', 'cloud.json', 'binding.json', 'recording-receipts.json')
    optional = ('capture-compaction.json', 'text-compaction.json', 'sqlite-compaction.json', 'recording-compaction.json', 'independent-scores-verification.json',
                'independent-resources-verification.json', 'observation-gateway-minute05.json')
    for directory in args.directories:
        repeat = json.loads((directory / 'binding.json').read_text())['repeat']
        for name in required:
            include(directory / name, f'repeat-{repeat}/' + name)
        for name in optional:
            if (directory / name).exists():
                include(directory / name, f'repeat-{repeat}/' + name)
    manifest = {name: {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                for name, raw in sorted(selected.items())}
    selected['case-manifest.json'] = json.dumps(manifest, indent=2).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, 'w:gz') as archive:
        for name, raw in sorted(selected.items()):
            assert credentials.search(raw) is None
            if Path(name).suffix == '.json':
                json.loads(raw)
            elif Path(name).suffix == '.jsonl':
                for line in raw.splitlines():
                    json.loads(line)
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
