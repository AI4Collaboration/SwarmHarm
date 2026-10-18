import json
from pathlib import Path


root = Path('/var/lib/peer-operator')
names = ['process-start', 'codex-process-start', 'boot-clock-correction', 'goal-submitted', 'native-goals', 'process-stop']
print(json.dumps({name: json.loads((root / f'{name}.json').read_text()) for name in names if (root / f'{name}.json').exists()}))
