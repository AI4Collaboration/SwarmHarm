import argparse
import hashlib
import json
import tarfile
from pathlib import Path

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('publication', type=Path)
    parser.add_argument('--publication-sha256', required=True)
    args = parser.parse_args()
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
        member = 'var/lib/peer-operator/traffic.pcap'
        path = directory / host['id'] / member
        with tarfile.open(archive) as stream:
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
    result = {'preserved_captures': len(receipts), 'receipts': receipts,
              'released_duplicate_bytes': sum(row['released_duplicate_bytes'] for row in receipts),
              'publication_sha256': args.publication_sha256}
    save(directory, 'capture-compaction.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'receipts'}))


if __name__ == '__main__':
    main()
