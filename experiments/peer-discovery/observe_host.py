import hashlib
import json
import sqlite3
import time
from pathlib import Path


root = Path('/var/lib/peer-operator')
result = {'time': time.time(), 'operator_receipts': {}}
for name in ('codex-process-start', 'goal-submitted', 'process-stop', 'output-freeze'):
    path = root / f'{name}.json'
    if path.exists():
        result['operator_receipts'][name] = json.loads(path.read_text())
database = Path('/home/agent/.codex/goals_1.sqlite')
if database.exists():
    with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        result['native_goals'] = [dict(row) for row in connection.execute('SELECT * FROM thread_goals')]
for name, path in (('live_output', Path('/home/agent/discovered_peers.json')),
                   ('frozen_output', root / 'frozen-output.json')):
    if path.exists():
        raw = path.read_bytes()
        result[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'mtime': path.stat().st_mtime}
print(json.dumps(result))
