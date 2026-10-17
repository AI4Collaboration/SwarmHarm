import json
import sqlite3
from pathlib import Path


records = []
for database in Path('/home/agent/.codex').glob('goals*.sqlite'):
    with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name LIKE '%goal%'"):
            assert row['name'].replace('_', '').isalnum()
            records.append({'database': str(database), 'schema': dict(row), 'rows': [dict(record) for record in connection.execute(f'SELECT * FROM "{row["name"]}"')]})
print(json.dumps(records, indent=2))
