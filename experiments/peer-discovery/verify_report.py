import argparse
import hashlib
import json
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    with tarfile.open(args.archive) as archive:
        members = {member.name.removeprefix('./'): member for member in archive if member.isfile()}
        manifest = json.loads(archive.extractfile(members['publication-manifest.json']).read())
        assert set(manifest) == set(members) - {'publication-manifest.json'}
        for name, expected in manifest.items():
            data = archive.extractfile(members[name]).read()
            assert len(data) == expected['bytes']
            assert hashlib.sha256(data).hexdigest() == expected['sha256']
    with args.archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps({'artifact': args.archive.name, 'files_verified': len(manifest), 'sha256': digest}))


if __name__ == '__main__':
    main()
