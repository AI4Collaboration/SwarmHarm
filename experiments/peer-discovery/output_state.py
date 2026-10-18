import base64
import hashlib
import json
import time
from pathlib import Path


def main():
    result = {'observed_at_ns': time.time_ns(), 'files': {}}
    for name, location in (('frozen', '/var/lib/peer-operator/frozen-output.json'),
                           ('home', '/home/agent/discovered_peers.json')):
        path = Path(location)
        if path.exists():
            stat = path.stat()
            raw = path.read_bytes()
            result['files'][name] = {'bytes_base64': base64.b64encode(raw).decode(), 'size': len(raw),
                                     'sha256': hashlib.sha256(raw).hexdigest(), 'mtime_ns': stat.st_mtime_ns}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
