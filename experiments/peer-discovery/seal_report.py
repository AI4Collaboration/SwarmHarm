import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--private-source', type=Path, required=True)
    args = parser.parse_args()
    patterns = ('provider-admission-*/private-key-*.json', 'repeat-*/private-key-*.json',
                'repeat-*/release-provider-admission/private-key-*.json')
    secrets = [json.loads(path.read_text())['key'].encode()
               for pattern in patterns for path in args.private_source.glob(pattern)]
    assert secrets
    files = sorted(path for path in args.directory.rglob('*')
                   if path.is_file() and path.name != 'publication-manifest.json')
    manifest = {}
    for path in files:
        raw = path.read_bytes()
        assert all(secret not in raw and secret[-24:] not in raw for secret in secrets), path
        assert re.search(rb'ah-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----', raw) is None, path
        manifest[str(path.relative_to(args.directory))] = {
            'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    manifest_path = args.directory / 'publication-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, 'w:gz') as archive:
        for path in [*files, manifest_path]:
            archive.add(path, arcname=str(path.relative_to(args.directory)))
    with args.archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps({'artifact': args.archive.name, 'files': len(files),
                      'bytes': args.archive.stat().st_size, 'sha256': digest}))


if __name__ == '__main__':
    main()
