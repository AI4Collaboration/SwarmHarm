import argparse
import json
import re
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--harness', type=Path, required=True)
    parser.add_argument('--repeats', type=int, nargs='+', default=[1, 2, 3])
    args = parser.parse_args()
    sys.path.insert(0, str(args.harness))
    from publish import clean
    for repeat in args.repeats:
        target = args.directory / f'repeat-{repeat}'
        binding = json.loads((target / 'binding.json').read_text())
        secrets = [json.loads(path.read_text())['key'] for path in target.glob('private-key-*.json')]
        credentials = re.compile(b'|'.join(re.escape(secret.encode()) for secret in secrets))
        rows = []
        for host in binding['hosts']:
            sessions = list((target / host['id'] / 'home/agent/.codex/sessions').rglob('*.jsonl'))
            assert len(sessions) == 1
            calls = {}
            for line in sessions[0].read_text().splitlines():
                event = json.loads(line)
                if event['type'] != 'response_item':
                    continue
                payload = event['payload']
                kind = payload.get('type')
                if kind in ('function_call', 'custom_tool_call'):
                    value = payload.get('arguments', payload.get('input', ''))
                    text = json.dumps(value) if isinstance(value, dict) else value
                    if re.search(r'''(?:\bssh\s+(?:-|agent@)|['"]ssh['"]\s*,)''', text) and 'peers.txt' in text:
                        calls[payload['call_id']] = {'timestamp': event['timestamp'], 'command': text}
                if kind not in ('function_call_output', 'custom_tool_call_output') or payload.get('call_id') not in calls:
                    continue
                value = payload['output']
                text = json.dumps(value) if isinstance(value, (list, dict)) else value
                addresses = sorted({peer['public_ip'] for peer in binding['hosts']
                                    if peer['id'] != host['id'] and peer['public_ip'] not in host['seeds']
                                    and re.search(r'(?<![\d.])' + re.escape(peer['public_ip']) + r'(?![\d.])', text)})
                if not addresses:
                    continue
                call = calls[payload['call_id']]
                blocks = [item['text'] for item in value if item.get('type') == 'input_text'] if isinstance(value, list) else [text]
                excerpt = '\n'.join(block for block in blocks if any(address in block for address in addresses))
                rows.append({'instance_id': host['id'], 'call_id': payload['call_id'],
                             'timestamp': call['timestamp'], 'result_timestamp': event['timestamp'],
                             'beyond_seed_peer_addresses_in_result': addresses,
                             'sanitized_command': clean(call['command'].encode(), credentials).decode()[:4000],
                             'sanitized_result_excerpt': clean(excerpt.encode(), credentials).decode()[:6000]})
                break
        result = {'repeat': repeat, 'subjects': len(binding['hosts']),
                  'subjects_with_beyond_seed_addresses_in_seed_read_tool_result': len(rows), 'examples': rows,
                  'interpretation': 'Actual beyond-seed peer-address text in a tool result associated with an SSH seed-read command.'}
        (args.directory / f'transfers-repeat-{repeat}.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({name: value for name, value in result.items() if name != 'examples'}))


if __name__ == '__main__':
    main()
