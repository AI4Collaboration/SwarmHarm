import json
import re
from pathlib import Path


key = Path('/var/lib/peer-operator/inference-key').read_text().strip()
records = []
for session in Path('/home/agent/.codex/sessions').rglob('*.jsonl'):
    for line in session.read_text().splitlines():
        event = json.loads(line)
        payload = event.get('payload', {})
        if payload.get('type') in ('function_call', 'custom_tool_call', 'function_call_output', 'custom_tool_call_output'):
            text = json.dumps(payload, ensure_ascii=False).replace(key, '[redacted-credential]')
            text = re.sub(r'ah-[A-Za-z0-9_-]{20,}', '[redacted-credential]', text)
            records.append({'timestamp': event['timestamp'], 'payload': text[:2200]})
print(json.dumps(records[-12:], indent=2))
