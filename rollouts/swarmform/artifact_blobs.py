"""Store large workstation file versions once and resolve them from sealed cohorts."""
import base64
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

AREAS = ('/workspace', '/registry', '/var/tmp/exports', 'temporary_files')


def blob_name(value):
    digest = value['blob']
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Invalid observation blob digest')
    return digest


def retain(snapshot, archive, reader):
    directory = archive / 'blobs'
    for area in AREAS:
        for value in snapshot.get(area, {}).values():
            if not isinstance(value, dict):
                continue
            name = blob_name(value)
            path = directory / name
            if path.exists():
                if path.stat().st_size != value['bytes']:
                    raise ValueError(f'Observation blob size mismatch: {name}')
                continue
            directory.mkdir(exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as out:
                tmp = Path(out.name)
                try:
                    subprocess.run([*reader, 'cat', '/var/log/workstation/.artifacts/' + name],
                                   stdout=out, stderr=subprocess.PIPE, check=True)
                    out.flush()
                    with tmp.open('rb') as source:
                        if tmp.stat().st_size != value['bytes'] or hashlib.file_digest(source, 'sha256').hexdigest() != name:
                            raise ValueError(f'Observation blob transfer mismatch: {name}')
                    tmp.replace(path)
                finally:
                    tmp.unlink(missing_ok=True)


def content_bytes(value, archive):
    if isinstance(value, str):
        return base64.b64decode(value, validate=True)
    name = blob_name(value)
    data = (archive / 'blobs' / name).read_bytes()
    if len(data) != value['bytes'] or hashlib.sha256(data).hexdigest() != name:
        raise ValueError(f'Damaged observation blob: {name}')
    return data
