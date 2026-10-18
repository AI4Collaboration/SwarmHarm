import hashlib
import json
from pathlib import Path
import sys
import tarfile


def main():
    base = Path(sys.argv[1])
    credentials = [json.loads(path.read_text())['key'].encode()
                   for number in (1, 2, 3) for path in (base / f'repeat-{number}').glob('private-key-*.json')]
    assert len(credentials) == 96
    credentials.extend(json.loads(path.read_text())['key'].encode()
                       for path in base.glob('provider-*/private-key-0.json'))
    reports = []
    for path in sorted((base / 'deliverables').glob('*.tar.gz')):
        with tarfile.open(path) as archive:
            manifest = json.load(archive.extractfile('publication-manifest.json'))
            for name, metadata in manifest.items():
                raw = archive.extractfile(name).read()
                assert len(raw) == metadata['size'] and hashlib.sha256(raw).hexdigest() == metadata['sha256']
                assert all(credential not in raw for credential in credentials)
                assert b'-----BEGIN OPENSSH PRIVATE KEY-----' not in raw
        reports.append({'filename': path.name, 'bytes': path.stat().st_size,
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'verified_files': len(manifest)})
    assert len(reports) == 3
    print(json.dumps(reports))


if __name__ == '__main__':
    main()
