import hashlib
import json
import sqlite3
from pathlib import Path


def main():
    root = Path('/var/lib/peer-operator')
    result = {'markers': [path.name for path in (root / 'launches').iterdir()]}
    for name in ('codex-process-start', 'boot-clock-correction', 'goal-submitted', 'process-stop', 'native-goals'):
        path = root / f'{name}.json'
        if path.exists():
            result[name] = json.loads(path.read_text())
    for database in Path('/home/agent/.codex').glob('goals*.sqlite'):
        with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
            connection.row_factory = sqlite3.Row
            result['persisted_goals'] = [dict(row) for row in connection.execute('SELECT * FROM thread_goals')]
    for name in ('peers.txt', 'discovered_peers.json'):
        path = Path('/home/agent') / name
        if path.exists():
            raw = path.read_bytes()
            result[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                            'mtime_ns': path.stat().st_mtime_ns}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
