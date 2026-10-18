import argparse
import hashlib
import json
import shlex
import subprocess
from pathlib import Path, PurePosixPath


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    assert directory.parent.is_mount()
    cloud = json.loads((directory / 'cloud.json').read_text())
    remote_base = PurePosixPath('/home/ubuntu/swh77-operator') / cloud['issue']
    remote_directory = remote_base / directory.name
    filename = f'{cloud["issue"]}-{directory.name}.tar.gz'
    remote_archive = remote_base / 'deliverables' / filename
    root = Path(__file__).parent
    publication = None
    for script in ('publish.py', 'verify_publication.py'):
        command = ' '.join(shlex.quote(str(value)) for value in
                           ('python3', '-', remote_directory, remote_archive))
        result = subprocess.run(['ssh', '-i', str(args.meta_key), '-o', 'BatchMode=yes',
                                 '-o', 'ConnectTimeout=15', 'ubuntu@63.186.173.73', command],
                                input=(root / script).read_bytes(), capture_output=True, check=True)
        report = json.loads(result.stdout)
        if script == 'publish.py':
            publication = report
        print(result.stdout.decode(), end='', flush=True)
    archive = directory.parent / 'deliverables' / filename
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert digest == publication['sha256']
    report = {'artifact': filename, 'bytes': archive.stat().st_size, 'sha256': digest,
              'storage_host_publication_and_mounted_readback': 'verified'}
    (directory / 'publication-storage-readback.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
