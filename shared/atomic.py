"""Small durable-write helpers shared by maintained experiments."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile


def utc():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value, *, compact=False, sync=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            encoded = (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                       if compact else json.dumps(value, ensure_ascii=False, indent=2))
            stream.write(encoded.encode() + b"\n")
            stream.flush()
            if sync:
                os.fsync(stream.fileno())
        os.replace(temporary, path)
        if sync:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
