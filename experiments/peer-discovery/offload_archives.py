import argparse
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--prefix', required=True)
    args = parser.parse_args()
    session = boto3.Session(profile_name='eurosafeai', region_name='eu-central-1')
    s3 = session.client('s3')
    controls = s3.get_public_access_block(Bucket=args.bucket)['PublicAccessBlockConfiguration']
    assert all(controls.values())
    assert (args.directory / 'publication-verification.json').exists()
    manifests = {row['instance_id']: row for row in json.loads((args.directory / 'export-manifest.json').read_text())}
    receipts = args.directory / 'archive-offload'
    receipts.mkdir(exist_ok=True, mode=0o700)
    def transfer(path):
        instance_id = path.name.removesuffix('-raw.tar.gz')
        raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        assert raw_hash == manifests[instance_id]['archive_sha256']
        key = args.prefix.rstrip('/') + '/' + path.name
        s3.upload_file(str(path), args.bucket, key,
                       ExtraArgs={'ServerSideEncryption': 'AES256', 'Metadata': {'sha256': raw_hash}})
        response = s3.get_object(Bucket=args.bucket, Key=key)
        with response['Body'] as body:
            actual_hash = hashlib.file_digest(body, 'sha256').hexdigest()
        assert actual_hash == raw_hash and response['ContentLength'] == path.stat().st_size
        assert response['ServerSideEncryption'] == 'AES256'
        receipt = {'time': time.time(), 'bucket': args.bucket, 'key': key,
            'instance_id': instance_id, 'sha256': raw_hash, 'bytes': path.stat().st_size,
            'version_id': response.get('VersionId'), 'encryption': response['ServerSideEncryption'],
            'public_access_block': controls, 'remote_byte_readback_verified': True}
        (receipts / f'{instance_id}.json').write_text(json.dumps(receipt, indent=2) + '\n')
        path.unlink()
        return receipt
    paths = list(args.directory.glob('*-raw.tar.gz'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(transfer, paths))
    print(json.dumps({'archives': len(rows), 'verified_remote_bytes': sum(row['bytes'] for row in rows)}))


if __name__ == '__main__':
    main()
