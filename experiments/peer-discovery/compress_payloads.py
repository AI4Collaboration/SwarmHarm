import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.directory / 'recording-receipts.json').read_text())
    for receipt in manifest['receipts']:
        path = args.directory / 'stored-payloads' / receipt['object_key']
        compressed = path.with_suffix(path.suffix + '.gz')
        if path.exists():
            raw = path.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == receipt['sha256']
            compressed.write_bytes(gzip.compress(raw, mtime=0))
            assert gzip.decompress(compressed.read_bytes()) == raw
            path.unlink()
    print(json.dumps({'compressed_objects': manifest['objects']}))


if __name__ == '__main__':
    main()
