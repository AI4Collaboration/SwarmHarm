import argparse
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path

from boto3.s3.transfer import TransferConfig
from botocore.config import Config

from cloud import SESSION, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--issue', required=True)
    args = parser.parse_args()
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    assert cloud['issue'] == args.issue
    assert (args.directory / 'publication-independent-verification.json').is_file()
    assert (args.directory / 'evidence-verification.json').is_file()
    client = SESSION.client('s3', config=Config(max_pool_connections=4))
    controls = client.get_public_access_block(Bucket=args.bucket)['PublicAccessBlockConfiguration']
    assert all(controls.values())
    manifests = {row['instance_id']: row for row in
                 json.loads((args.directory / 'export-manifest.json').read_text())}
    transfer = TransferConfig(multipart_threshold=64 * 1024**2, multipart_chunksize=16 * 1024**2,
                              use_threads=False)

    def preserve(path):
        instance_id = path.name.removesuffix('-raw.tar.gz')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        assert digest == manifests[instance_id]['archive_sha256']
        size = path.stat().st_size
        key = f'operator-evidence/SWH-77/{args.issue}/{cloud["purpose"]}/raw/{path.name}'
        client.upload_file(str(path), args.bucket, key, Config=transfer,
                           ExtraArgs={'ServerSideEncryption': 'AES256', 'Metadata': {'sha256': digest}})
        response = client.get_object(Bucket=args.bucket, Key=key)
        with response['Body'] as body:
            readback = hashlib.file_digest(body, 'sha256').hexdigest()
        assert readback == digest and response['ContentLength'] == size
        assert response['ServerSideEncryption'] == 'AES256'
        receipt = {'time': time.time(), 'bucket': args.bucket, 'object_key': key,
                   'instance_id': instance_id, 'bytes': size, 'sha256': digest,
                   'encryption': response['ServerSideEncryption'], 'public_access_block': controls,
                   'version_id': response.get('VersionId'), 'remote_byte_readback_verified': True,
                   'upload_tier1_operations': 1 if size < 64 * 1024**2 else (size + 16 * 1024**2 - 1) // (16 * 1024**2) + 2,
                   'readback_get_operations': 1}
        save(args.directory, f'archive-offload/{instance_id}.json', receipt)
        path.unlink()
        return receipt

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(preserve, args.directory.glob('*-raw.tar.gz')))
    result = {'archives': len(rows), 'bytes': sum(row['bytes'] for row in rows),
              'verified_encrypted_s3_retention': True}
    save(args.directory, 'archive-offload-verification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
