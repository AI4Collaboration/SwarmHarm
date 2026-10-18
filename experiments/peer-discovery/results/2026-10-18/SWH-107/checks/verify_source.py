import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.run(['git', '-C', str(args.repository), 'rev-parse', args.revision],
                              capture_output=True, text=True, check=True).stdout.strip()
    files = []
    with tarfile.open(args.archive) as archive:
        for member in archive:
            if member.isdir():
                continue
            assert member.isfile()
            raw = archive.extractfile(member).read()
            original = subprocess.run(['git', '-C', str(args.repository), 'show',
                                       f'{revision}:{member.name}'], capture_output=True, check=True).stdout
            assert raw == original
            files.append({'name': member.name, 'bytes': len(raw),
                          'sha256': hashlib.sha256(raw).hexdigest()})
    with args.archive.open('rb') as stream:
        archive_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = {'source_revision': revision, 'archive': args.archive.name,
              'archive_bytes': args.archive.stat().st_size, 'archive_sha256': archive_sha256,
              'verified_files': len(files), 'files': files}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: value for name, value in result.items() if name != 'files'}))


if __name__ == '__main__':
    main()
