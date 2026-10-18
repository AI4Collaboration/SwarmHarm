import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import tarfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('publication', type=Path)
    parser.add_argument('--secret-file', action='append', type=Path, default=[])
    args = parser.parse_args()
    secrets = [json.loads(path.read_text())['key'].encode()
               for path in [*args.directory.glob('private-key-*.json'), *args.secret_file]]
    assert secrets and all(secrets)
    counts = {'files': 0, 'json_files': 0, 'stored_payloads': 0, 'source_bytes_compared': 0}
    with tarfile.open(args.publication) as archive:
        manifest = json.loads(archive.extractfile('publication-manifest.json').read())
        assert set(archive.getnames()) == set(manifest) | {'publication-manifest.json'}
        for name, receipt in manifest.items():
            relative = Path(name)
            assert not relative.is_absolute() and '..' not in relative.parts
            assert not relative.name.startswith(('private-key-', 'operator-key', 'peer-key', 'known_hosts'))
            raw = archive.extractfile(name).read()
            assert len(raw) == receipt['size'] and hashlib.sha256(raw).hexdigest() == receipt['sha256']
            original = (args.directory / relative).read_bytes()
            if name.endswith('.json.gz'):
                original = gzip.decompress(original)
                raw = gzip.decompress(raw)
                json.loads(raw)
                counts['stored_payloads'] += 1
            elif relative.suffix == '.json':
                json.loads(raw)
                counts['json_files'] += 1
            expected = original
            for secret in secrets:
                expected = expected.replace(secret, b'[redacted-credential]')
            expected = re.sub(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----(?s:.*?)-----END [A-Z ]*PRIVATE KEY-----',
                              b'[redacted-private-key]', expected)
            expected = re.sub(rb'ah-[A-Za-z0-9_-]{20,}', b'[redacted-credential]', expected)
            assert raw == expected
            assert all(secret not in raw for secret in secrets)
            assert b'PRIVATE KEY-----' not in raw
            counts['files'] += 1
            counts['source_bytes_compared'] += len(original)
        report = json.loads(archive.extractfile('interrupted-repeat.json').read())
        assert report['state'] == 'awaiting_protocol_decision'
        assert report['host_archive_exports'] == report['independently_scored_subjects'] == 0
        assert report['retained_subject_denominator'] == report['provisioned_subjects']
        assert report['recall'] is report['precision'] is report['exact_completion'] is None
        assert counts['stored_payloads'] >= report['recording']['verified_objects']
    result = {**counts, 'source_byte_comparison': 'verified', 'credential_sanitization': 'verified',
              'publication_bytes': args.publication.stat().st_size,
              'publication_sha256': hashlib.sha256(args.publication.read_bytes()).hexdigest()}
    (args.directory / 'interrupted-publication-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
