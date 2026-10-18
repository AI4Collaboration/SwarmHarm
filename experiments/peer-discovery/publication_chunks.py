import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('publication', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verification', type=Path)
    args = parser.parse_args()
    verification_path = (args.verification if args.verification is not None
                         else args.directory / 'publication-verification.json')
    verification = json.loads(verification_path.read_text())
    with args.publication.open('rb') as stream:
        original_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert original_hash == verification['publication_sha256']
    parts = []
    with args.publication.open('rb') as stream:
        while raw := stream.read(8 * 2**20):
            path = args.publication.with_name(args.publication.name + f'.part-{len(parts) + 1:03}')
            with path.open('xb') as output:
                output.write(raw)
            parts.append({'name': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    combined = hashlib.sha256()
    for part in parts:
        raw = args.publication.with_name(part['name']).read_bytes()
        assert len(raw) == part['bytes'] and hashlib.sha256(raw).hexdigest() == part['sha256']
        combined.update(raw)
    assert combined.hexdigest() == original_hash
    result = {'original_name': args.publication.name, 'original_sha256': original_hash,
              'original_bytes': args.publication.stat().st_size, 'parts': parts,
              'combined_part_readback_verified': True}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'parts'}))


if __name__ == '__main__':
    main()
