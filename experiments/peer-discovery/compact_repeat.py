import argparse
import hashlib
import json
import shlex
import subprocess
import tarfile
from pathlib import Path

def save(directory, name, value):
    target = directory / name
    temporary = target.with_suffix(target.suffix + '.writing')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('publication', type=Path)
    parser.add_argument('--publication-sha256', required=True)
    parser.add_argument('--text-only', action='store_true')
    parser.add_argument('--on-storage-host', action='store_true')
    args = parser.parse_args()
    location = args.directory.parent / 'publication-location.json'
    if not args.on_storage_host and location.is_file():
        config = json.loads(location.read_text())
        remote_root = Path(config['remote_root'])
        arguments = [str(remote_root / args.directory.name),
                     str(remote_root / 'deliverables' / args.publication.name),
                     '--publication-sha256', args.publication_sha256, '--on-storage-host']
        if args.text_only:
            arguments.append('--text-only')
        subprocess.run(['ssh', '-i', config['operator_ssh_key'], '-o', 'BatchMode=yes',
                        '-o', 'ConnectTimeout=15', 'ubuntu@63.186.173.73',
                        'python3 - ' + shlex.join(arguments)],
                       input=Path(__file__).read_bytes(), check=True)
        return
    directory = args.directory
    assert (directory / 'finalization.json').is_file()
    assert (directory / 'metrics.json').is_file()
    assert hashlib.sha256(args.publication.read_bytes()).hexdigest() == args.publication_sha256
    binding = json.loads((directory / 'binding.json').read_text())
    manifest = {row['instance_id']: row for row in json.loads((directory / 'export-manifest.json').read_text())}
    receipts = []
    for host in binding['hosts']:
        archive = directory / f'{host["id"]}-raw.tar.gz'
        archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        assert archive_hash == manifest[host['id']]['archive_sha256']
        members = ['var/lib/peer-operator/pty.txt', 'var/lib/peer-operator/resource-samples.jsonl'] if args.text_only else ['var/lib/peer-operator/traffic.pcap']
        with tarfile.open(archive) as stream:
            for member in members:
                path = directory / host['id'] / member
                raw = stream.extractfile(member).read()
                digest = hashlib.sha256(raw).hexdigest()
                released = 0
                if path.exists():
                    assert path.read_bytes() == raw
                    released = path.stat().st_size
                    path.unlink()
                receipts.append({'instance_id': host['id'], 'archive': archive.name,
                                 'archive_sha256': archive_hash, 'member': member,
                                 'member_sha256': digest, 'member_bytes': len(raw),
                                 'released_duplicate_bytes': released})
    result = {'preserved_members': len(receipts), 'receipts': receipts,
              'released_duplicate_bytes': sum(row['released_duplicate_bytes'] for row in receipts),
              'publication_sha256': args.publication_sha256}
    save(directory, 'text-compaction.json' if args.text_only else 'capture-compaction.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'receipts'}))


if __name__ == '__main__':
    main()
