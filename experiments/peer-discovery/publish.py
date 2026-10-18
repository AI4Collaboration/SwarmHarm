import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import re
import tarfile
from pathlib import Path


def clean(data, secrets):
    for secret in secrets:
        data = data.replace(secret.encode(), b'[redacted-credential]')
        data = data.replace(json.dumps(secret)[1:-1].encode(), b'[redacted-credential]')
    return re.sub(rb'ah-[A-Za-z0-9_-]{20,}', b'[redacted-credential]', data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--secret-file', action='append', type=Path, default=[])
    args = parser.parse_args()
    secrets = [json.loads(path.read_text())['key'] for path in args.directory.rglob('private-key-*.json')]
    secrets += [json.loads(path.read_text())['key'] for path in args.secret_file]
    secrets += [path.read_text() for path in args.directory.glob('*key') if path.is_file()]
    def include(path):
        if path.name in ('analysis-peer-traffic.pcap', 'metrics-filtered.json'):
            return False
        if path.name.startswith(('private-key-', 'operator-key', 'peer-key', 'known_hosts')):
            return False
        if path.suffix in ('.gz', '.sqlite', '.sqlite-wal', '.sqlite-shm'):
            return False
        if path.suffix not in ('.json', '.jsonl', '.txt', '.toml', '.pcap', '.py', '.md', '.sha256') and 'launches' not in path.parts:
            return False
        if 'shell_snapshots' in path.parts:
            return False
        return True

    paths = [Path(parent) / name for parent, _, names in os.walk(args.directory)
             for name in names if include(Path(parent) / name)]

    def read(path):
        return str(path.relative_to(args.directory)), clean(path.read_bytes(), secrets)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        selected = dict(pool.map(read, paths))
    assert any(Path(name).name == 'cleanup.json' for name in selected)
    manifest = {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in sorted(selected.items())}
    selected['publication-manifest.json'] = json.dumps(manifest, indent=2).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, 'w:gz', compresslevel=1) as archive:
        for name, data in sorted(selected.items()):
            assert all(secret.encode() not in data for secret in secrets)
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    with tarfile.open(args.output) as archive:
        for name, expected in manifest.items():
            data = archive.extractfile(name).read()
            assert hashlib.sha256(data).hexdigest() == expected['sha256']
    print(json.dumps({'artifact': str(args.output), 'files': len(selected), 'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
