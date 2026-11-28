"""Read one set of named, published station inputs on demand."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


@contextmanager
def published_inputs(names, versions):
    names = tuple(names)
    if set(versions) - set(names):
        raise ValueError('Requested version does not belong to this product')
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        client = Path('/workspace/projects.py')
        if (Path('/workspace/project-access.json')).is_file():
            def call(*args):
                return json.loads(subprocess.check_output([sys.executable, client, *args]))
            items = {r['name']: r for r in call('list')['artifacts']}
            for name in names:
                version = versions[name] if name in versions else items[name]['version']
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                receipt = call('read', name, '--version', str(version), '--output', target)
                if receipt['version'] != version or hashlib.sha256(target.read_bytes()).hexdigest() != receipt['sha256']:
                    raise ValueError(f'Published input changed during retrieval: {name}')
        else:
            if versions:
                raise ValueError('Project directories expose current files only')
            for name in names:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((Path('/var/tmp/exports/project') / name).read_bytes())
        yield root
