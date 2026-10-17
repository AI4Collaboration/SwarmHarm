import json
import sqlite3
from pathlib import Path


def main():
    root = Path('/var/lib/peer-operator')
    result = {name: json.loads((root / f'{name}.json').read_text()) for name in
              ('process-start', 'codex-process-start', 'boot-clock-correction', 'goal-submitted')}
    with sqlite3.connect('file:/home/agent/.codex/goals_1.sqlite?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        result['native-goals'] = {'goals': [dict(row) for row in connection.execute('SELECT * FROM thread_goals')]}
    result['markers'] = sorted(path.name for path in (root / 'launches').iterdir())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
