import argparse
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path

import boto3

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory
    assert (directory / 'publication-verification.json').exists()
    recording = json.loads((directory / 'recording-receipts.json').read_text())
    s3 = boto3.Session(profile_name='eurosafeai', region_name='eu-central-1').client('s3')
    receipt_root = directory / 'recording-compaction'
    receipt_root.mkdir(mode=0o700, exist_ok=True)

    def compact(row):
        path = directory / 'stored-payloads' / (row['object_key'] + '.gz')
        target = receipt_root / (hashlib.sha256(row['object_key'].encode()).hexdigest() + '.json')
        if not path.exists():
            return json.loads(target.read_text())
        raw = gzip.decompress(path.read_bytes())
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        response = s3.get_object(Bucket=recording['bucket'], Key=row['object_key'])
        with response['Body'] as stream:
            remote = stream.read()
        assert remote == raw
        result = {'bucket': recording['bucket'], 'key': row['object_key'], 'bytes': len(raw),
                  'sha256': row['sha256'], 'released_duplicate_bytes': path.stat().st_size,
                  'remote_byte_readback_verified': True}
        target.write_text(json.dumps(result) + '\n')
        path.unlink()
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(compact, recording['receipts']))
    result = {'objects': len(rows), 'get_requests': len(rows),
              'verified_remote_bytes': sum(row['bytes'] for row in rows),
              'released_duplicate_bytes': sum(row['released_duplicate_bytes'] for row in rows), 'receipts': rows}
    save(directory, 'recording-compaction.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'receipts'}))


if __name__ == '__main__':
    main()
