import argparse
import concurrent.futures
import hashlib
import json
import tarfile
from pathlib import Path

from cloud import save
from repeat import export_host, gateway
from recording import collect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    assert not (args.directory / 'termination.json').exists()

    def preserve(host):
        archive = args.directory / f'{host["id"]}-raw.tar.gz'
        if archive.exists():
            with tarfile.open(archive) as bundle:
                bundle.extractall(args.directory / host['id'], filter='data')
            with archive.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            receipt = {'instance_id': host['id'], 'archive_sha256': digest,
                       'archive_bytes': archive.stat().st_size, 'original_archive_retained': True}
            save(args.directory, f'host-export-receipts/{host["id"]}.json', receipt)
            return receipt
        return export_host(args.directory, host)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        receipts = list(pool.map(preserve, binding['hosts']))
    save(args.directory, 'export-manifest.json', receipts)
    completeness = {host['id']: {name: (args.directory / host['id'] / 'var/lib/peer-operator' / name).is_file()
                                for name in ('process-stop.json', 'native-goals.json', 'collection-receipt.json')}
                    for host in binding['hosts']}
    save(args.directory, 'collection-completeness.json', completeness)
    assert all(all(row.values()) for row in completeness.values())
    print(json.dumps({'original_host_archives': len(receipts), 'lifecycle_receipts': 'verified'}), flush=True)
    for index, host in enumerate(binding['hosts']):
        key = json.loads((args.directory / f'private-key-{index}.json').read_text())
        save(args.directory, f'gateway-{index}.json', gateway(args.meta_key, 'export', key['id']))
    collect(args.directory)


if __name__ == '__main__':
    main()
