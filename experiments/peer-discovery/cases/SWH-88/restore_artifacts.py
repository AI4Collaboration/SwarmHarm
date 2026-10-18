import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('downloads', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--verify-and-clean', action='store_true')
    args = parser.parse_args()
    artifacts = json.loads(args.manifest.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    for artifact in artifacts:
        destination = args.output / artifact['artifact']
        assert destination.name == artifact['artifact']
        digest = hashlib.sha256()
        size = 0
        with destination.open('xb') as target:
            for part in artifact['parts']:
                source = args.downloads / part['file']
                encoded = source.read_bytes()
                assert len(encoded) == part['bytes']
                assert hashlib.sha256(encoded).hexdigest() == part['sha256']
                with zipfile.ZipFile(source) as archive:
                    assert archive.namelist() == [part['part']]
                    raw = archive.read(part['part'])
                assert len(raw) == part['part_bytes']
                assert hashlib.sha256(raw).hexdigest() == part['part_sha256']
                target.write(raw)
                digest.update(raw)
                size += len(raw)
        assert size == artifact['bytes'] and digest.hexdigest() == artifact['sha256']
        print(json.dumps({'artifact': artifact['artifact'], 'bytes': size, 'sha256': digest.hexdigest()}))
        if args.verify_and_clean:
            destination.unlink()
    if args.verify_and_clean:
        args.output.rmdir()


if __name__ == '__main__':
    main()
