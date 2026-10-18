import base64
import hashlib
import json
import time
from pathlib import Path


def main():
    files = {}
    for path in (Path('/home/agent/discovered_peers.json'), Path('/var/lib/peer-operator/frozen-output.json')):
        if path.exists():
            raw = path.read_bytes()
            stat = path.stat()
            files[str(path)] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'mtime_ns': stat.st_mtime_ns, 'base64': base64.b64encode(raw).decode()}
    print(json.dumps({'observed_at_ns': time.time_ns(), 'files': files}))


if __name__ == '__main__':
    main()
