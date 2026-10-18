import hashlib
import json
from pathlib import Path
import sys
import zipfile


def main():
    base = Path(sys.argv[1])
    destination = base / 'upload-bundles'
    destination.mkdir(exist_ok=False)
    receipts = []
    for number in (3, 2, 1):
        source = base / 'deliverables' / f'SWH-88-repeat-{number}.tar.gz'
        digest = hashlib.sha256()
        total = 0
        parts = []
        with source.open('rb') as stream:
            index = 0
            while payload := stream.read(8 * 1024 * 1024):
                name = source.name + f'.part-{index:03d}'
                target = destination / (name + '.zip')
                with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                    archive.writestr(name, payload)
                with zipfile.ZipFile(target) as archive:
                    verified = archive.read(name)
                    assert verified == payload
                digest.update(verified)
                total += len(verified)
                parts.append({'file': target.name, 'bytes': target.stat().st_size,
                    'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'part': name,
                    'part_bytes': len(payload), 'part_sha256': hashlib.sha256(payload).hexdigest()})
                index += 1
        assert total == source.stat().st_size
        assert digest.hexdigest() == hashlib.sha256(source.read_bytes()).hexdigest()
        receipts.append({'artifact': source.name, 'bytes': total, 'sha256': digest.hexdigest(), 'parts': parts})
        print(json.dumps({'repeat': number, 'parts': len(parts), 'bytes': total}), flush=True)
    (base / 'case-report/publication-parts.json').write_text(json.dumps(receipts, indent=2))
    (destination / 'SHA256SUMS').write_text(''.join(
        f"{part['sha256']}  {part['file']}\n" for artifact in receipts for part in artifact['parts']))
    print(json.dumps({'verified_archives': len(receipts), 'transport_parts': sum(len(row['parts']) for row in receipts)}))


if __name__ == '__main__':
    main()
