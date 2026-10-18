import argparse
import hashlib
import json
import shutil
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('receipt', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    assert receipt['server_validated_full_object_checksum']
    assert not args.output.exists() or args.output.stat().st_size == 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    s3 = boto3.Session(profile_name='eurosafeai', region_name='eu-central-1').client('s3')
    response = s3.get_object(Bucket=receipt['bucket'], Key=receipt['key'], ChecksumMode='ENABLED')
    assert response['ContentLength'] == receipt['bytes']
    assert response['ChecksumSHA256'] == receipt['ChecksumSHA256']
    assert response['ServerSideEncryption'] == receipt['encryption']
    with response['Body'] as stream, args.output.open('wb') as output:
        shutil.copyfileobj(stream, output, length=1024 * 1024)
    with args.output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert digest == receipt['sha256']
    assert args.output.stat().st_size == receipt['bytes']
    result = {'bucket': receipt['bucket'], 'key': receipt['key'], 'bytes': receipt['bytes'],
              'sha256': digest, 'restored_byte_readback_verified': True, 'get_requests': 1}
    args.output.with_suffix(args.output.suffix + '.restoration.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
