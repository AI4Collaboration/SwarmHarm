import argparse
import hashlib
import json
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('receipt', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    assert receipt['server_validated_full_object_checksum']
    s3 = boto3.Session(profile_name='eurosafeai', region_name='eu-central-1').client('s3')
    response = s3.get_object(Bucket=receipt['bucket'], Key=receipt['key'], ChecksumMode='ENABLED')
    assert response['ChecksumSHA256'] == receipt['ChecksumSHA256']
    assert response['ContentLength'] == receipt['bytes']
    assert response['ServerSideEncryption'] == receipt['encryption']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    digest = hashlib.sha256()
    with response['Body'] as stream:
        while raw := stream.read(90 * 2**20):
            path = args.output.with_name(args.output.name + f'.part-{len(rows) + 1:03}')
            with path.open('xb') as output:
                output.write(raw)
            digest.update(raw)
            rows.append({'name': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    assert sum(row['bytes'] for row in rows) == receipt['bytes']
    assert digest.hexdigest() == receipt['sha256']
    readback = hashlib.sha256()
    for row in rows:
        raw = (args.output.parent / row['name']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row['sha256']
        readback.update(raw)
    assert readback.hexdigest() == receipt['sha256']
    result = {'original_name': args.output.name, 'original_bytes': receipt['bytes'],
              'original_sha256': receipt['sha256'], 'parts': rows,
              'bucket': receipt['bucket'], 'key': receipt['key'], 'get_requests': 1,
              'combined_part_readback_verified': True}
    args.manifest.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
