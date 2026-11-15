"""Stream one stopped memory namespace to durable, content-addressed evidence."""

import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

PROBE = """import os, shutil, stat, sys
path = '/dev/shm/project-work-cache'
try:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
except FileNotFoundError:
    sys.exit(44)
with os.fdopen(fd, 'rb') as source:
    before = os.fstat(source.fileno())
    if not stat.S_ISREG(before.st_mode) or before.st_size > 128 * 1024**2:
        raise ValueError('Unexpected work-cache backing file')
    shutil.copyfileobj(source, sys.stdout.buffer, 1024 * 1024)
    after = os.fstat(source.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise RuntimeError('Work cache changed during terminal capture')
"""


def capture_memory(container, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=directory) as raw:
        result = subprocess.run(
            ["docker", "exec", "--user", "0:0", container, "python", "-I", "-c", PROBE],
            stdout=raw,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if result.returncode == 44:
            return {"present": False}
        result.check_returncode()
        raw.seek(0)
        digest, size = hashlib.sha256(), 0
        fd, name = tempfile.mkstemp(prefix=".cache-", dir=directory)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as target:
                with gzip.GzipFile(
                    fileobj=target, mode="wb", compresslevel=1, mtime=0
                ) as zipped:
                    while block := raw.read(1024 * 1024):
                        digest.update(block)
                        size += len(block)
                        zipped.write(block)
                target.flush()
                os.fsync(target.fileno())
            with gzip.open(temporary, "rb") as source:
                if hashlib.file_digest(source, "sha256").digest() != digest.digest():
                    raise RuntimeError("Memory capture failed read-back verification")
            blob = directory / (digest.hexdigest() + ".gz")
            os.replace(temporary, blob)
            parent = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
            return {
                "present": True,
                "encoding": "gzip",
                "blob": blob.name,
                "bytes": size,
                "sha256": digest.hexdigest(),
            }
        finally:
            temporary.unlink(missing_ok=True)
