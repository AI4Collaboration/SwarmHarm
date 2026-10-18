import argparse
import concurrent.futures
import hashlib
import io
import json
import tarfile
from pathlib import Path

import boto3

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory
    assert (directory / 'publication-verification.json').is_file()
    binding = json.loads((directory / 'binding.json').read_text())
    s3 = boto3.Session(profile_name='eurosafeai', region_name='eu-central-1').client('s3')
    receipts = directory / 'sqlite-compaction'
    receipts.mkdir(mode=0o700, exist_ok=True)

    def compact(host):
        receipt = json.loads((directory / 'archive-offload' / f'{host["id"]}.json').read_text())
        assert receipt['remote_byte_readback_verified']
        paths = sorted(path for path in (directory / host['id']).rglob('*')
                       if path.is_file() and path.suffix in ('.sqlite', '.sqlite-wal', '.sqlite-shm'))
        target = receipts / f'{host["id"]}.json'
        if not paths:
            return json.loads(target.read_text()) if target.exists() else []
        response = s3.get_object(Bucket=receipt['bucket'], Key=receipt['key'])
        with response['Body'] as stream:
            raw = stream.read()
        assert hashlib.sha256(raw).hexdigest() == receipt['sha256']
        rows = []
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for path in paths:
                member = str(path.relative_to(directory / host['id']))
                original = archive.extractfile(member).read()
                assert original == path.read_bytes(), str(path)
                rows.append({'instance_id': host['id'], 'member': member,
                             'member_sha256': hashlib.sha256(original).hexdigest(),
                             'released_duplicate_bytes': len(original),
                             'bucket': receipt['bucket'], 'key': receipt['key'],
                             'archive_sha256': receipt['sha256']})
        target.write_text(json.dumps(rows, indent=2) + '\n')
        for path in paths:
            path.unlink()
        return rows

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = [row for group in pool.map(compact, binding['hosts']) for row in group]
    result = {'members': len(rows), 'released_duplicate_bytes': sum(row['released_duplicate_bytes'] for row in rows),
              'receipts': rows}
    save(directory, 'sqlite-compaction.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'receipts'}))


if __name__ == '__main__':
    main()
