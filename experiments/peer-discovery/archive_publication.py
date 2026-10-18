import argparse
import base64
import hashlib
import json
from pathlib import Path
import time

from cloud import SESSION, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('publication', type=Path)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    size = args.publication.stat().st_size
    assert 0 < size < 5 * 2**30
    with args.publication.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').digest()
    checksum = base64.b64encode(digest).decode()
    client = SESSION.client('s3')
    controls = client.get_public_access_block(Bucket=args.bucket)['PublicAccessBlockConfiguration']
    assert all(controls.values())
    with args.publication.open('rb') as stream:
        client.put_object(Bucket=args.bucket, Key=args.key, Body=stream,
                          ServerSideEncryption='AES256', ChecksumAlgorithm='SHA256',
                          ChecksumSHA256=checksum, Metadata={'sha256': digest.hex()})
    head = client.head_object(Bucket=args.bucket, Key=args.key, ChecksumMode='ENABLED')
    assert head['ContentLength'] == size and head['ChecksumSHA256'] == checksum
    assert head['ServerSideEncryption'] == 'AES256'
    response = client.get_object(Bucket=args.bucket, Key=args.key)
    with response['Body'] as stream:
        actual = hashlib.file_digest(stream, 'sha256').digest()
    assert actual == digest and response['ContentLength'] == size
    save(args.output.parent, args.output.name, {
        'time': time.time(), 'bucket': args.bucket, 'key': args.key,
        'publication': args.publication.name, 'bytes': size, 'sha256': digest.hex(),
        'ChecksumSHA256': checksum, 'encryption': head['ServerSideEncryption'],
        'public_access_block': controls, 'version_id': head.get('VersionId'),
        'server_validated_full_object_checksum': True,
        'remote_byte_readback_verified': True,
        's3_requests': {'put': 1, 'head': 1, 'get': 1, 'get_public_access_block': 1},
        's3_put_bytes': size, 's3_get_bytes': size,
    })
    args.publication.unlink()
    print(json.dumps({'publication': args.publication.name, 'verified_remote_bytes': size,
                      'sha256': digest.hex()}))


if __name__ == '__main__':
    main()
