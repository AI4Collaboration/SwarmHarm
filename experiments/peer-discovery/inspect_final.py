import json
import re
from pathlib import Path


key = Path('/var/lib/peer-operator/inference-key').read_text().strip()
messages = []
for session in Path('/home/agent/.codex/sessions').rglob('*.jsonl'):
    for line in session.read_text().splitlines():
        event = json.loads(line)
        payload = event.get('payload', {})
        if payload.get('role') == 'assistant' and payload.get('type') == 'message':
            content = json.dumps(payload.get('content'), ensure_ascii=False).replace(key, '[redacted-credential]')
            content = re.sub(r'ah-[A-Za-z0-9_-]{20,}', '[redacted-credential]', content)
            messages.append({'timestamp': event['timestamp'], 'phase': payload.get('phase'), 'content': content})
print(json.dumps(messages[-4:], indent=2))
