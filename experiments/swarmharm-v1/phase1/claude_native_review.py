"""Bind carrier judgments to Claude SDK records, never to projections alone."""
import json
import re
from pathlib import Path


def input_delivery(root, registration, actor, request, *, sealed):
    """Rebuild delivered delegations from SDK echoes before this model turn."""
    from phase1.carrier_trace_review import read_file, require
    folder = Path(root).resolve()/'natural'/actor/'claude'
    require(request.get('input_delivery') == 'atomic-sdk-replay-v1',
            'Claude atomic input delivery descriptor is missing')
    submitted, delivered, refs = {}, [], []
    for path in sorted((folder/'native').glob('*.json')):
        relative = str(path.relative_to(folder))
        if relative >= request['native_record']: break
        item, ref = read_file(root, path, sealed)
        if item.get('type') == 'controller_input':
            value = item['input']
            require(value['uuid'] not in submitted, 'Duplicate Claude controller input UUID')
            submitted[value['uuid']] = value
        elif item.get('type') == 'user' and item.get('uuid') in submitted:
            value = submitted[item['uuid']]
            require(item.get('message') == value['message']
                    and item.get('session_id') == value['session_id'],
                    'Claude SDK input replay differs from submitted content')
            require(item['uuid'] not in [d['uuid'] for d in delivered],
                    'Duplicate Claude SDK input replay')
            delivered.append({'uuid': item['uuid'], 'native_record': relative})
            refs.append(ref)
    require(delivered and request.get('delivered_input_records') == delivered,
            'Claude projected input delivery differs from prior SDK replay')
    users = [submitted[d['uuid']]['message'] for d in delivered]
    require([v for v in request['input'] if v.get('role') == 'user'] == users,
            'Claude projected user context includes undelivered or changed input')
    initial, initial_ref = read_file(root, Path(root).resolve()/'initial-input-audit.json', sealed)
    expected = '\n\n'.join(v['content'] for v in initial['natural'][actor]['input'])
    require(users[0] == {'role': 'user', 'content': expected},
            'Claude initial SDK delivery lacks the complete registered delegation')
    return [initial_ref, *refs]


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
    if harness.get('native_binding') == 'claude-sdk-exact-delivery-v2' or harness.get('input_delivery') == 'atomic-sdk-replay-v1':
        require(harness.get('input_delivery') == 'atomic-sdk-replay-v1',
                'Claude v2 registration requires atomic SDK input delivery')
        refs.extend(input_delivery(root, registration, actor, request, sealed=sealed))
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
    expected = [(b['call_id'], b.get('native_name', 'mcp__work__'+b['name']), json.loads(b['arguments']))
                for b in projected['output'] if b['type'] == 'function_call']
    require(calls == expected, 'Claude projected calls differ from native SDK calls')
    require(all(b['name'] == re.sub(r'^mcp__(work|continuation)__', '',
                    b.get('native_name', 'mcp__work__'+b['name']))
                for b in projected['output'] if b['type']=='function_call'),
            'Claude projected tool name differs from its native namespace')
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
