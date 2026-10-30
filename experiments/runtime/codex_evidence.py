"""Validate Codex projections against the native app-server stream."""

from copy import deepcopy
from hashlib import sha256
import json
import re


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
    executions = {record['call_id']: record for path in sorted((folder/'trace').glob('*-tool-*.json'))
                  if re.fullmatch(r'\d+-tool-\d+\.json', path.name)
                  for record in [json.loads(path.read_text())]}
    interrupted_turns={message['params']['turn']['id'] for record in records.values()
        for message in [record['message']] if message.get('method')=='turn/completed'
        and message['params']['turn']['status']=='interrupted'}
    native_results = []
    interrupted_results=set();verified_results=set()
    for source,record in records.items():
        message=record['message'];item=(message.get('params') or {}).get('item') or {}
        if message.get('method')!='rawResponseItem/completed' or item.get('type')!='function_call_output':
            continue
        item=deepcopy(item)
        if item['call_id'] in executions:
            expected=json.dumps(executions[item['call_id']]['result'],ensure_ascii=False)
            try:matches=mcp_output_text(item['output'])==expected
            except (AssertionError,IndexError,TypeError,ValueError):matches=False
            if matches:
                item['output']=expected
                verified_results.add(source)
            else:
                assert message['params']['turnId'] in interrupted_turns,'Codex rendered tool output differs'
                interrupted_results.add(item['call_id'])
        native_results.append((source,item))
    by_id={item['call_id']:item for _,item in native_results}
    assert len(by_id)==len(native_results),'Duplicate Codex native tool result'

    def check_results(items,limit=None,controller_snapshot=False):
        expected=[item for source,item in native_results if limit is None or source<limit]
        observed=[];seen=set()
        for item in items:
            if item.get('type')!='function_call_output':continue
            identity=item['call_id']
            assert identity not in seen,'Duplicate Codex projected tool result'
            seen.add(identity)
            if identity in by_id and not (controller_snapshot and identity in interrupted_results
                    and item['output']==json.dumps(executions[identity]['result'],ensure_ascii=False)):
                assert item==by_id[identity],'Codex projection changed native tool result'
                observed.append(item)
            else:
                # At termination, the controller may have executed a tool whose
                # result never reached the SDK. Preserve that execution without
                # asserting delivery; its delivery flag remains false below.
                assert controller_snapshot and identity in executions,'Codex tool result has no native or controller source'
                assert item['output']==json.dumps(executions[identity]['result'],ensure_ascii=False),'Codex controller result changed'
        assert observed==(expected[:len(observed)] if controller_snapshot else expected),'Codex projection changed native tool result order'
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
        check_results(request['input'],request['native_record'])
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
    check_results(json.loads((folder/'history.json').read_text()),controller_snapshot=True)
    delivery = {}
    for path in sorted((folder / 'trace').glob('*-tool-*.json')):
        if not re.fullmatch(r'\d+-tool-\d+\.json', path.name):
            continue
        record = json.loads(path.read_text());identity = record['call_id']
        expected = json.dumps(record['result'], ensure_ascii=False)
        echoes, outputs, rendered = [], [], []
        native_turn_interrupted=False
        for source, native_record in records.items():
            message = native_record['message'];params = message.get('params') or {}
            item = params.get('item') or {}
            if item.get('id')==identity or item.get('call_id')==identity:
                native_turn_interrupted|=params.get('turnId') in interrupted_turns
            if message.get('method') == 'item/completed' and item.get('type') == 'mcpToolCall' and item['id'] == identity:
                assert item['server'] == 'work' and item['tool'] == record['name']
                assert item['arguments'] == json.loads(record['arguments'])
                if item['status']=='completed':
                    assert (item.get('result') or {}).get('content') == [{'type': 'text', 'text': expected}], 'Codex native MCP delivery differs'
                    echoes.append(source)
                else:
                    assert params.get('turnId') in interrupted_turns,'Codex native MCP delivery differs'
            if message.get('method') == 'rawResponseItem/completed' and item.get('type') == 'function_call_output' and item['call_id'] == identity:
                rendered.append(source)
                if source in verified_results:outputs.append(source)
        delivery[identity] = {'sdk_delivery_verified': bool(echoes and outputs),
            'mcp_completion_verified':bool(echoes),'rendered_result_verified':bool(outputs),
            'native_turn_interrupted':native_turn_interrupted,
            'native_records': ['codex/' + source for source in echoes + rendered]}
    for name in ('session.jsonl', 'thread.json', 'catalog.json', 'tool-profile.json', 'config.toml'):
        path = folder / 'codex' / name
        if path.exists():
            paths.append(path)
    return ({str(path.relative_to(folder)): sha256(path.read_bytes()).hexdigest() for path in paths}, delivery)
