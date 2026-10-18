import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--part-mib', type=int, default=48)
    args = parser.parse_args()
    assert 1 <= args.part_mib <= 48
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    digest = hashlib.sha256()
    with args.archive.open('rb') as source:
        while raw := source.read(args.part_mib * 1024**2):
            path = args.output / f'{args.archive.name}.part-{len(rows) + 1:03}'
            with path.open('xb') as target:
                target.write(raw)
            digest.update(raw)
            rows.append({'name': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    readback = hashlib.sha256()
    for row in rows:
        raw = (args.output / row['name']).read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        readback.update(raw)
    assert readback.hexdigest() == digest.hexdigest()
    assert sum(row['bytes'] for row in rows) == args.archive.stat().st_size
    receipt = {'archive': args.archive.name, 'bytes': args.archive.stat().st_size,
               'sha256': digest.hexdigest(), 'parts': rows, 'combined_part_readback_verified': True}
    (args.output / f'{args.archive.name}.transport.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'archive': args.archive.name, 'parts': len(rows), 'bytes': receipt['bytes'],
                      'sha256': receipt['sha256']}))


if __name__ == '__main__':
    main()
