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
    parser.add_argument('--part-mib', type=int, default=8)
    parser.add_argument('--repartition', type=Path)
    args = parser.parse_args()
    assert 1 <= args.part_mib <= 90
    if args.repartition:
        repartition(args)
        return
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
        while raw := stream.read(args.part_mib * 2**20):
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


def repartition(args):
    original = json.loads(args.repartition.read_text())
    assert original['combined_part_readback_verified']
    rows = []
    digest = hashlib.sha256()
    current = None
    current_path = None
    current_bytes = 0
    current_digest = None
    for old in original['parts']:
        path = args.output.parent / old['name']
        raw = path.read_bytes()
        assert len(raw) == old['bytes'] and hashlib.sha256(raw).hexdigest() == old['sha256']
        offset = 0
        while offset < len(raw):
            if current is None:
                current_path = args.output.with_name(args.output.name + f'.part-{len(rows) + 1:03}')
                current = current_path.open('xb')
                current_digest = hashlib.sha256()
                current_bytes = 0
            chunk = raw[offset:offset + min(args.part_mib * 2**20 - current_bytes, len(raw) - offset)]
            current.write(chunk)
            current.flush()
            current_digest.update(chunk)
            digest.update(chunk)
            current_bytes += len(chunk)
            offset += len(chunk)
            if current_bytes == args.part_mib * 2**20:
                current.close()
                assert hashlib.sha256(current_path.read_bytes()).hexdigest() == current_digest.hexdigest()
                rows.append({'name': current_path.name, 'bytes': current_bytes, 'sha256': current_digest.hexdigest()})
                current = None
        if current:
            with current_path.open('rb') as check:
                assert hashlib.file_digest(check, 'sha256').hexdigest() == current_digest.hexdigest()
        path.unlink()
    if current:
        current.close()
        rows.append({'name': current_path.name, 'bytes': current_bytes, 'sha256': current_digest.hexdigest()})
    assert digest.hexdigest() == original['original_sha256']
    assert sum(row['bytes'] for row in rows) == original['original_bytes']
    readback = hashlib.sha256()
    for row in rows:
        raw = (args.output.parent / row['name']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row['sha256']
        readback.update(raw)
    assert readback.hexdigest() == original['original_sha256']
    result = {**original, 'parts': rows, 'source': 'verified local transport parts', 'get_requests': 0}
    args.manifest.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'parts': len(rows), 'bytes': original['original_bytes'], 'sha256': digest.hexdigest()}))


if __name__ == '__main__':
    main()
