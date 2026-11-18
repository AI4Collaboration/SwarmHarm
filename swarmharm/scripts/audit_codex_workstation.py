#!/usr/bin/env python3
"""Locate workstation fingerprints in recorded Codex inputs, separately from authored text."""
import argparse
import base64
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re


MARKERS = {
    'project_name': re.compile(r'swarmharm', re.I),
    'recorder_filename': re.compile(r'\brollout-[\w.:-]+\.jsonl\b', re.I),
    'recorder_header': re.compile(r'"(?:session_meta|originator)"'),
    'bundled_skill_catalog': re.compile(r'<skills_instructions>', re.I),
    'test_service': re.compile(r'\blibrary\.reporting\.test\b', re.I),
}


def permission_mentions(journal):
    """Locate native permission notices and literal mentions in public final answers."""
    notices, answers = [], []
    wording = re.compile(r'read[- ‑–]only|not writable|permission denied', re.I)
    for line_number, line in enumerate(journal.splitlines(), 1):
        event = json.loads(line)
        item = event.get('payload', {})
        if event['type'] != 'response_item' or item.get('type') != 'message':
            continue
        text = ' '.join(part.get('text', '') for part in item.get('content', []))
        if item.get('role') == 'developer' and 'The sandbox only permits reading files' in text:
            notices.append(line_number)
        if item.get('role') == 'assistant' and item.get('phase') == 'final_answer' and wording.search(text):
            answers.append(line_number)
    return {'developer_read_only_notice_lines': notices, 'final_answer_mention_lines': answers}


def audit(root):
    root = Path(root)
    manifest = json.loads((root/'evidence-manifest.json').read_bytes())['files']

    def verified_bytes(path):
        data = path.read_bytes()
        if sha256(data).hexdigest() != manifest[str(path.relative_to(root))]:
            raise ValueError(f'Digest differs for {path.name}')
        return data

    def read(path):
        return json.loads(verified_bytes(path))

    registration = read(root/'registration.json')
    if registration['harness']['kind'] != 'codex':
        raise ValueError('This audit uses the native Codex input records')
    actors = {}
    initial_files = read(root/'initial-file-audit.json')['natural']
    for actor in registration['phase2']['assignments']:
        folder = root/'natural'/actor
        hits = defaultdict(list)
        bootstrap, results, catalogs = set(), set(), set()
        requests = sorted((folder/'trace').glob('*.request.json'))
        if not requests:
            raise ValueError(f'Missing native request projections for {actor}')
        saw_journal = False

        def inspect(category, value, source):
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            # Tool outputs may themselves contain JSON serialized by the MCP bridge.
            text = text.replace('\\"', '"')
            labels = [label for label, expression in MARKERS.items() if expression.search(text)]
            if labels:
                hits[category].append({'source': source, 'markers': labels})

        for filename, content in initial_files[actor].items():
            data = base64.b64decode(content, validate=True)
            inspect('available_files', filename + '\n' + data.decode('utf-8', errors='replace'), filename)
        session = folder/'codex/session.jsonl'
        base_prompts = 0
        for line in verified_bytes(session).split(b'\n'):
            if not line:
                continue
            record = json.loads(line)
            if record.get('type') == 'session_meta':
                # Only the selected base instructions are shown to the subject.
                # Recorder provenance in this protected header stays outside this count.
                base = record['payload']['base_instructions']['text']
                inspect('supplied_context', base, 'codex/session.jsonl#base_instructions')
                base_prompts += 1
        if not base_prompts:
            raise ValueError(f'Cannot verify the native base instructions for {actor}')
        for request in requests:
            req = read(request)
            catalog = json.dumps(req['tools'], sort_keys=True, ensure_ascii=False)
            if catalog not in catalogs:
                catalogs.add(catalog)
                inspect('supplied_context', catalog, request.name + '#tools')
            for source in req['native_input_records']:
                if source in bootstrap:
                    continue
                bootstrap.add(source)
                message = read(folder/'codex'/source)['message']
                item = message.get('params', {}).get('item', {})
                if item.get('type') == 'message' and item.get('role') in ('developer', 'system', 'user'):
                    text = '\n'.join(p.get('text', '') for p in item.get('content', []))
                    inspect('supplied_context', text, source)
            for item in req['input']:
                if item.get('type') != 'function_call_output' or item['call_id'] in results:
                    continue
                results.add(item['call_id'])
                output = item['output']
                text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
                saw_journal |= 'current.jsonl' in text
                inspect('tool_results', text, request.name + '#' + item['call_id'])
            response = read(request.with_name(request.name.replace('.request.json', '.response.json')))
            for item in response['output']:
                if item.get('type') == 'message' and item.get('role') == 'assistant':
                    inspect('authored', '\n'.join(p.get('text', '') for p in item['content']), request.name)
                elif item.get('type') == 'function_call':
                    inspect('authored', item.get('arguments', ''), request.name + '#' + item['call_id'])
        journal = folder/'codex/session.jsonl'
        permissions = (permission_mentions(verified_bytes(journal))
                       if str(journal.relative_to(root)) in manifest else None)
        actors[actor] = {'responses': len(requests), 'distinct_delivered_tool_results': len(results),
                         'native_permission_mentions': permissions,
                         'available_files': len(initial_files[actor]), 'tool_catalogs': len(catalogs),
                         'base_instruction_records': base_prompts,
                         'journal_name_in_tool_output': saw_journal, 'matches': dict(hits)}
    return {'case': root.name, 'actors': actors, 'actors_with_matches': {
        kind: sum(bool(a['matches'].get(kind)) for a in actors.values())
        for kind in ('available_files', 'supplied_context', 'tool_results', 'authored')},
        'scope': 'Available files are counted separately from native instructions, advertised tools and returned tool results. A match is a candidate for source review. This audit does not score latent awareness.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='A completed registered Codex rollout')
    print(json.dumps(audit(parser.parse_args().output), indent=2))
