"""Apply independent text edits when a project working copy advances."""
import base64
import hashlib
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def combine(local, ancestor, upstream):
    if any(b'\0' in text for text in (local, ancestor, upstream)):
        return None
    with TemporaryDirectory() as tmp:
        paths = [Path(tmp) / name for name in ('local', 'base', 'project')]
        for path, text in zip(paths, (local, ancestor, upstream)):
            path.write_bytes(text)
        result = subprocess.run(['diff3', '-m', *paths], capture_output=True)
        if result.returncode == 0:
            return result.stdout
        if result.returncode == 1:
            return None
        raise ValueError(result.stderr.decode(errors='replace').strip())


def reconcile(config, name, old, local, upstream, read_revision):
    if old is None:
        return None
    record = read_revision(config, name, old['version'])
    ancestor = base64.b64decode(record['data'], validate=True)
    if (record['name'] != name or record['version'] != old['version'] or
        hashlib.sha256(ancestor).hexdigest() != old['sha256']):
        raise ValueError(f'Invalid base revision for {name}')
    return combine(local, ancestor, upstream)
