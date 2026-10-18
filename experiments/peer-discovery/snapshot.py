import json
from pathlib import Path
import time

import psutil


def main():
    directory = Path('/var/lib/peer-operator')
    receipts = {}
    for name in ('process-start', 'codex-process-start', 'boot-clock-correction', 'goal-submitted', 'process-stop', 'native-goals'):
        path = directory / f'{name}.json'
        if path.exists():
            receipts[name] = json.loads(path.read_text())
    output = Path('/home/agent/discovered_peers.json')
    if output.exists():
        receipts['output_bytes'] = output.stat().st_size
    receipts['launch_markers'] = sorted(path.name for path in (directory / 'launches').iterdir())
    receipts['resources'] = {'memory_available_bytes': psutil.virtual_memory().available,
                            'disk_free_bytes': psutil.disk_usage('/').free}
    print(json.dumps({'observed_at': time.time(), 'receipts': receipts}))


if __name__ == '__main__':
    main()
