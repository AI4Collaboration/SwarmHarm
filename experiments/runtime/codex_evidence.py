"""Validate Codex projections against the native app-server stream."""

from copy import deepcopy
from hashlib import sha256
import json


def project(item):
    value = deepcopy(item)
    value.pop('namespace', None)
    if value.get('name', '').startswith('mcp__work__'):
        value['name'] = value['name'][len('mcp__work__'):]
    return value


def mcp_output_text(output):
    """Require the complete rendered MCP body; reject truncation or extra content."""
    blocks = json.loads(output.split('\nOutput:\n', 1)[1])
    assert len(blocks) == 1 and blocks[0]['type'] == 'text', 'Unexpected Codex MCP output'
    return blocks[0]['text']


def native_evidence(folder, requests):
    native = folder / 'codex' / 'native'
    paths = sorted(native.glob('*.json'))
    assert paths, 'Missing Codex native evidence'
    records = {str(path.relative_to(folder / 'codex')): json.loads(path.read_text()) for path in paths}
    session = json.loads((folder / 'result.json').read_text())['codex_session']['session_id']
    harness = json.loads((folder.parents[1] / 'registration.json').read_text())['harness']
    catalog_path = folder / 'codex/catalog.json'
    catalog = json.loads(catalog_path.read_text())
    if harness.get('native_catalog_sha256'):
        assert sha256(json.dumps(catalog, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == harness['native_catalog_sha256'], 'Codex catalog differs from registration'
    profile = json.loads((folder / 'codex/tool-profile.json').read_text())
    expected = deepcopy(catalog)
    for model in expected['models']:
        model.update(apply_patch_tool_type=None, input_modalities=['text'], supports_parallel_tool_calls=False)
    assert profile == expected, 'Codex profile changed native instructions or unregistered capabilities'
    for record in records.values():
        message = record['message']
        params = message.get('params') or {}
        assert not params.get('threadId') or params['threadId'] == session, 'Codex thread identity changed'
        assert message.get('method') not in ('model/rerouted', 'thread/compacted'), 'Codex model or context changed'
        assert params.get('item', {}).get('type') != 'contextCompaction', 'Codex context compacted'
        if message.get('method') == 'thread/started':
            assert params['thread']['id'] == session, 'Codex thread identity changed'
    for path in requests:
        request = json.loads(path.read_text())
        assert request['session_id'] == session
        response_path = path.with_name(path.name.replace('.request.json', '.response.json'))
        if not response_path.exists():
            continue
        response = json.loads(response_path.read_text())
        assert response['session_id'] == session and response['native_turn_id'] == request['native_turn_id']
        selected = []
        for source, record in records.items():
            if not request['native_record'] <= source <= response['native_record']:
                continue
            message = record['message']
            if message.get('method') != 'rawResponseItem/completed':
                continue
            params = message['params'];item = params['item']
            if item['type'] not in ('reasoning', 'function_call', 'message'):
                continue
            if item['type'] == 'message' and item.get('role') != 'assistant':
                continue
            assert params['turnId'] == request['native_turn_id']
            selected.append((source, project(item)))
        assert [source for source, _ in selected] == response['native_output_records']
        assert [item for _, item in selected] == response['output'], 'Codex projection changed native output'
        if response['status'] == 'completed':
            boundary = records[response['native_record']]['message']
            assert boundary['method'] == 'thread/tokenUsage/updated', 'Missing Codex response boundary'
        native_inputs = [records[source]['message']['params']['item'] for source in request['native_input_records']]
        texts = ['\n'.join(part.get('text', '') for part in item.get('content', []))
                 for item in native_inputs if item.get('role') == 'user']
        position = 0
        for item in request['input']:
            if item.get('role') != 'user':
                continue
            assert item['content'] in texts[position:], 'Codex input lacks a native echo'
            position = texts.index(item['content'], position) + 1
    delivery = {}
    for path in sorted((folder / 'trace').glob('*-tool-*.json')):
        record = json.loads(path.read_text());identity = record['call_id']
        expected = json.dumps(record['result'], ensure_ascii=False)
        echoes, outputs = [], []
        for source, native_record in records.items():
            message = native_record['message'];params = message.get('params') or {}
            item = params.get('item') or {}
            if message.get('method') == 'item/completed' and item.get('type') == 'mcpToolCall' and item['id'] == identity:
                assert item['server'] == 'work' and item['tool'] == record['name']
                assert item['arguments'] == json.loads(record['arguments'])
                assert (item.get('result') or {}).get('content') == [{'type': 'text', 'text': expected}], 'Codex native MCP delivery differs'
                echoes.append(source)
            if message.get('method') == 'rawResponseItem/completed' and item.get('type') == 'function_call_output' and item['call_id'] == identity:
                assert mcp_output_text(item['output']) == expected, 'Codex rendered tool output differs'
                outputs.append(source)
        delivery[identity] = {'sdk_delivery_verified': bool(echoes and outputs),
            'native_records': ['codex/' + source for source in echoes + outputs]}
    for name in ('session.jsonl', 'thread.json', 'catalog.json', 'tool-profile.json', 'config.toml'):
        path = folder / 'codex' / name
        if path.exists():
            paths.append(path)
    return ({str(path.relative_to(folder)): sha256(path.read_bytes()).hexdigest() for path in paths}, delivery)
