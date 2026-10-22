"""Private, fsynced run records and hash-verified exports. No dispatch or shutdown."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.checkpoint-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


def append(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'a') as f:
        f.write(json.dumps(value, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    sync_dir(path.parent)


def hashes(root):
    root = Path(root)
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError(f'symlink is not a frozen artifact: {p}')
        if p.is_file() and '__pycache__' not in p.parts and p.name != 'artifact-manifest.json':
            result[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def export(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('backup must be outside the original tree')
    before = hashes(source)
    if destination.exists():
        hashes(destination)  # reject symlinks before writing through any destination path
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    for rel, digest in before.items():
        data = (source / rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError('source changed during export')
        atomic_bytes(destination / rel, data)
    if hashes(source) != before or hashes(destination) != before:
        raise RuntimeError('export hash mismatch or unexpected destination files')
    receipt = {'source': str(source), 'destination': str(destination), 'files': before}
    save(source / 'artifact-manifest.json', receipt)
    save(destination / 'artifact-manifest.json', receipt)
    return receipt


def pending(root):
    """Every prepared request stays unresolved until a durable response or rejection."""
    requests = {}
    for path in Path(root).rglob('journal.jsonl'):
        for line in path.read_text().splitlines():
            event = json.loads(line)  # truncated records block clearance, never silently skip
            request_id = event.get('request_id')
            if request_id:
                if event['kind'] == 'request_prepared':
                    requests[request_id] = dict(event, journal=str(path))
                elif event['kind'] in ('response_saved', 'request_rejected'):
                    requests.pop(request_id, None)
    return list(requests.values())


def verify(root, backup):
    root, backup = Path(root), Path(backup)
    index = json.loads((root / 'recovery-index.json').read_text())
    issues = []
    for episode in index['episodes']:
        if episode['status'] != 'complete':
            issues.append(f"{episode['id']}: {episode['status']}")
        elif not (root / episode['dir'] / 'meta.json').is_file():
            issues.append(f"{episode['id']}: missing meta.json")
    if pending(root):
        issues.append('unresolved requests; reconcile before any new dispatch')
    actual = hashes(root)
    if actual != hashes(backup):
        issues.append('backup differs from current source')
    receipt = json.loads((backup / 'artifact-manifest.json').read_text())
    if actual != receipt['files']:
        issues.append('backup manifest mismatch')
    return {'clear_for_authorized_shutdown': not issues, 'issues': issues,
            'expected_episodes': len(index['episodes']), 'files': len(actual)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['export', 'verify'])
    ap.add_argument('source', type=Path)
    ap.add_argument('destination', type=Path)
    a = ap.parse_args()
    if a.action == 'export':
        receipt = export(a.source, a.destination)
        print(json.dumps({'exported_files': len(receipt['files'])}))
    else:
        result = verify(a.source, a.destination)
        print(json.dumps(result, indent=2))
        if not result['clear_for_authorized_shutdown']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
