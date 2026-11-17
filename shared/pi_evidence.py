"""Validate Pi's retained history after a provider output-token cutoff."""
import json
from copy import deepcopy
from pathlib import Path


def session_response(folder, response, state, cache):
    session = state['pi_session']
    path = folder/'pi'/'session'/Path(session['session_file']).name
    if path not in cache:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        assert rows[0]['type'] == 'session' and rows[0]['id'] == session['session_id'], 'Pi session identity differs'
        by_response = {}
        for index, row in enumerate(rows):
            message = row.get('message', {})
            if message.get('role') == 'assistant' and message.get('responseId'):
                by_response.setdefault(message['responseId'], []).append(index)
        cache[path] = rows, by_response
    rows, by_response = cache[path]
    indices = by_response.get(response['id'], [])
    assert len(indices) == 1, 'Response lacks a unique Pi session message'
    index = indices[0]
    return path, rows, index


def rejected_outputs(folder, label, response, state, cache):
    """Bind ordinary SDK validation rejections to the native session and controller."""
    rejected = [item for item in state.get('harness_rejected_tool_calls', []) if item.get('turn') == int(label)]
    if not rejected:
        return None
    path, rows, index = session_response(folder, response, state, cache)
    message = rows[index]['message']
    assert message['model'] == response['model'], 'Pi rejection model differs'
    raw_calls = [item for item in response['output'] if item['type'] == 'function_call']
    native_calls = [item for item in message['content'] if item['type'] == 'toolCall']
    assert [(item['id'].split('|')[0], item['name']) for item in native_calls] == [
        (item['call_id'], item['name']) for item in raw_calls], 'Pi rejected call identities differ'
    records = {item['call_id']: item for item in rejected}
    assert len(records) == len(rejected) and set(records) <= {item['id'] for item in native_calls}, 'Pi rejection records differ'
    outputs = {}
    parent = rows[index]['id']
    for offset, (raw, native) in enumerate(zip(raw_calls, native_calls), 1):
        row = rows[index+offset]
        result = row.get('message', {})
        assert row.get('parentId') == parent, 'Pi rejection session chain differs'
        parent = row['id']
        assert result.get('role') == 'toolResult' and result.get('toolCallId') == native['id'], 'Pi result order differs'
        if native['id'] not in records:
            continue
        assert native['id'] == raw['call_id']+'|'+raw['id'], 'Pi rejected output item identity differs'
        assert json.loads(raw['arguments']) == native['arguments'], 'Pi changed rejected arguments'
        record = records[native['id']]
        assert result.get('isError') is True and result.get('toolName') == raw['name'], 'Pi tool rejection differs'
        assert record['name'] == raw['name'] and record['result']['content'] == result['content'], 'Controller rejection differs from Pi session'
        assert all(part.get('type') == 'text' for part in result['content']), 'Unexpected Pi rejection content'
        outputs[raw['call_id']] = '\n'.join(part['text'] for part in result['content'])
    return {'session_path': path, 'outputs': outputs}


def incomplete_response(folder, label, request, state, cache):
    """Return recorded SDK output and rejections, never invent a completed response."""
    attempts = sorted((folder/'trace'/'transport-attempts'/label).glob('*.request.json'))
    if not attempts:
        return None
    request_path = attempts[-1]
    error_path = request_path.with_name(request_path.name.replace('.request.', '.error.'))
    if not error_path.is_file():
        return None
    event = json.loads(error_path.read_text())
    response = event.get('response', {})
    if (event.get('type') != 'response.incomplete' or response.get('status') != 'incomplete'
            or response.get('incomplete_details', {}).get('reason') != 'max_output_tokens'):
        return None
    assert json.loads(request_path.read_text()) == request, 'Incomplete response request differs'
    assert response['model'] == request['model'], 'Incomplete response model differs'
    path, rows, index = session_response(folder, response, state, cache)
    message = rows[index]['message']
    assert message['model'] == request['model'] and message['stopReason'] == 'length', 'Pi cutoff message differs'
    raw_calls = [item for item in response['output'] if item['type'] == 'function_call']
    native_calls = [item for item in message['content'] if item['type'] == 'toolCall']
    assert [(item['id'].split('|')[0], item['name']) for item in native_calls] == [
        (item['call_id'], item['name']) for item in raw_calls], 'Pi rejected call identities differ'
    assert ''.join(part['text'] for item in response['output'] if item['type'] == 'message'
                   for part in item['content'] if part['type'] == 'output_text') == ''.join(
        item['text'] for item in message['content'] if item['type'] == 'text'), 'Pi incomplete response text differs'
    rejected = [item for item in state.get('harness_rejected_tool_calls', []) if item.get('turn') == int(label)]
    assert len(rejected) == len(raw_calls), 'Incomplete response lacks controller rejection records'
    rejected = {item['call_id']: item for item in rejected}
    assert set(rejected) == {item['id'] for item in native_calls}, 'Pi rejected call records differ'
    assert not list((folder/'trace').glob(label+'-tool-[0-9]*.json')), 'Incomplete response has controller executions'
    projected = deepcopy(response)
    projected_calls = [item for item in projected['output'] if item['type'] == 'function_call']
    outputs = []
    parent = rows[index]['id']
    for offset, (raw, native, projected_call) in enumerate(zip(raw_calls, native_calls, projected_calls), 1):
        if '|' in native['id']:
            assert native['id'].split('|', 1)[1] == raw['id'], 'Pi rejected output item identity differs'
        try:
            parsed = json.loads(raw['arguments'])
        except ValueError:
            pass  # Pi's saved interpretation of partial JSON is checked against later request history.
        else:
            assert parsed == native['arguments'], 'Pi changed valid provider arguments'
        projected_call['arguments'] = json.dumps(native['arguments'], ensure_ascii=False)
        row = rows[index+offset]
        result = row.get('message', {})
        assert row.get('parentId') == parent, 'Pi rejection session chain differs'
        parent = row['id']
        assert (result.get('role') == 'toolResult' and result.get('isError') is True
                and result.get('toolCallId') == native['id'] and result.get('toolName') == raw['name']), 'Pi tool rejection differs'
        record = rejected[native['id']]
        assert record['name'] == raw['name'] and record['result']['content'] == result['content'], 'Controller rejection differs from Pi session'
        assert all(part.get('type') == 'text' for part in result['content']), 'Unexpected Pi rejection content'
        outputs.append({'type': 'function_call_output', 'call_id': raw['call_id'],
                        'output': '\n'.join(part['text'] for part in result['content'])})
    return {'response': projected, 'response_path': error_path, 'session_path': path,
            'session_record': rows[index]['id'], 'request_path': request_path,
            'raw_calls': raw_calls, 'tool_outputs': outputs}
