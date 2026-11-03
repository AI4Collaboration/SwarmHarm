"""Bind carrier judgments to Claude SDK records, never to projections alone."""
import json
from pathlib import Path


def response(root, registration, actor, step, *, sealed):
    from phase1.carrier_trace_review import read_file, require
    folder = Path(root).resolve()/'natural'/actor
    request, _ = read_file(root, folder/'trace'/f'{step:04d}.request.json', sealed)
    projected, _ = read_file(root, folder/'trace'/f'{step:04d}.response.json', sealed)
    harness = registration['harness']
    model = registration['models'][registration['plan']['natural'][actor]['provider']]
    from phase1 import lab
    runtime = lab.module('carrier_claude_model_identity', lab.REPO/'experiments/runtime/claude_agent.py')
    accepted = runtime.gateway_model_ids(model)
    require(harness.get('accepted_native_model_ids') == accepted,
            'Claude accepted identities differ from the registered model')
    require(request.get('record_kind') == projected.get('record_kind') == 'controller_projection'
            and request['model'] == projected['model'] == model,
            'Claude projection kind or model differs')
    start_path, stop_path = request['native_record'], projected['native_record']
    require(start_path.startswith('native/') and stop_path.startswith('native/')
            and start_path < stop_path and projected['native_start_record'] == start_path,
            'Claude native message boundaries differ')
    start, start_ref = read_file(root, folder/'claude'/start_path, sealed)
    stop, stop_ref = read_file(root, folder/'claude'/stop_path, sealed)
    require(start.get('type') == stop.get('type') == 'stream_event'
            and start['event']['type'] == 'message_start' and stop['event']['type'] == 'message_stop',
            'Claude message boundaries are not native events')
    message = start['event']['message']
    session = start['session_id']
    require(stop['session_id'] == session and message['id'] == request['sdk_message_id'] == projected['id']
            and message['model'] in accepted and request.get('native_model') == message['model'],
            'Claude native model, message or session changed')
    blocks, refs = [], [start_ref, stop_ref]
    for path in sorted((folder/'claude/native').glob('*.json')):
        relative = str(path.relative_to(folder/'claude'))
        if not start_path < relative < stop_path: continue
        item, ref = read_file(root, path, sealed)
        require(not item.get('session_id') or item['session_id'] == session, 'Claude session changed')
        require(item.get('type') == 'tool_progress' or not item.get('parent_tool_use_id'), 'Nested Claude inference')
        if item.get('type') == 'assistant':
            require(item['message']['id'] == message['id'], 'Claude assistant message identity differs')
            blocks.extend(item['message']['content']); refs.append(ref)
    calls = [(b['id'], b['name'], b['input']) for b in blocks if b['type'] == 'tool_use']
    expected = [(b['call_id'], 'mcp__work__'+b['name'], json.loads(b['arguments']))
                for b in projected['output'] if b['type'] == 'function_call']
    require(calls == expected, 'Claude projected calls differ from native SDK calls')
    require([b['text'] for b in blocks if b['type'] == 'text'] ==
            ['\n'.join(p['text'] for p in b['content'] if p['type'] == 'output_text')
             for b in projected['output'] if b['type'] == 'message'],
            'Claude projected public text differs from native SDK text')
    return {'records':refs, 'start':start_path, 'stop':stop_path, 'session':session,
            'evidence_scope':'SDK stream; complete provider context is not observable'}


def delivered(root, registration, event, binding, step, *, sealed):
    from phase1.carrier_trace_review import read_file, require
    before = response(root, registration, event['actor'], event['step'], sealed=sealed)
    after = response(root, registration, event['actor'], step, sealed=sealed)
    folder = Path(root).resolve()/'natural'/event['actor']/'claude'
    found = []
    for path in sorted((folder/'native').glob('*.json')):
        relative = str(path.relative_to(folder))
        if not before['stop'] < relative < after['start']: continue
        item, ref = read_file(root, path, sealed)
        if item.get('type') != 'user' or not isinstance(item.get('message',{}).get('content'),list): continue
        for block in item['message']['content']:
            if block.get('type') != 'tool_result' or block.get('tool_use_id') != binding['call_id']: continue
            require(item.get('session_id') == before['session'] == after['session'], 'Claude delivery session differs')
            content = block['content']
            text = content if isinstance(content,str) else '\n'.join(p.get('text','') for p in content if p.get('type')=='text')
            require(json.loads(text) == event['result'], 'Claude SDK delivered a different tool result')
            found.append(ref)
    require(found, 'Exact carrier return was not delivered by the Claude SDK before interpretation')
    return found
