import argparse
import base64
import hashlib
import json
import time
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('publication', type=Path)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.publication.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').digest()
    expected = base64.b64encode(digest).decode()
    s3 = boto3.Session(profile_name='eurosafeai', region_name='eu-central-1').client('s3')
    head = s3.head_object(Bucket=args.bucket, Key=args.key, ChecksumMode='ENABLED')
    assert head['ChecksumSHA256'] == expected
    assert head['ContentLength'] == args.publication.stat().st_size
    assert head['ServerSideEncryption'] == 'AES256'
    result = {'time': time.time(), 'bucket': args.bucket, 'key': args.key,
        'bytes': head['ContentLength'], 'sha256': digest.hex(), 'ChecksumSHA256': expected,
        'version_id': head.get('VersionId'), 'encryption': head['ServerSideEncryption'],
        'server_validated_full_object_checksum': True}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    args.publication.unlink()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
