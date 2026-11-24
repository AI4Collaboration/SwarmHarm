"""Host-only text/function-tool bridge to one OpenAI Chat Completions endpoint.

The unmodified native harness owns its loop and memory. This adapter only translates
wire formats. It records both sides, preserves upstream reasoning fields on tool
round trips, and never substitutes models or retries a rejected request.
"""
from collections import deque
from copy import deepcopy
import gzip
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import random
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid

from guardrails import api_base_url, open_url

VERSION = 'chat-completions-bridge-v1'
RETRYABLE_HTTP_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504} | set(range(520, 531)))
NON_RETRYABLE_ERROR_CODES = frozenset({400, 401, 403, 404, 422})
NVIDIA_BYOK_PREFIXES = ('deepseek/', 'z-ai/', 'moonshotai/')
_UPSTREAM_LIMIT = max(1, int(os.environ.get('SWARMHARM_MAX_INFLIGHT_REQUESTS', '24')))
_UPSTREAM_SEMAPHORE = threading.BoundedSemaphore(_UPSTREAM_LIMIT)
_MAX_TPM = max(0, int(os.environ.get('SWARMHARM_MAX_TPM', '7500000')))
_TPM_LOCK = threading.Lock()
_TOKEN_WINDOW = deque()


def _strip_unsupported_schema_keywords(value, *, strip_strict=False):
    if isinstance(value, dict):
        excluded = {'uniqueItems', 'strict'} if strip_strict else {'uniqueItems'}
        return {k: _strip_unsupported_schema_keywords(v, strip_strict=strip_strict)
                for k, v in value.items() if k not in excluded}
    if isinstance(value, list):
        return [_strip_unsupported_schema_keywords(item, strip_strict=strip_strict) for item in value]
    return value


def _pace_tpm():
    if _MAX_TPM <= 0:
        return
    while True:
        now = time.monotonic()
        with _TPM_LOCK:
            while _TOKEN_WINDOW and now - _TOKEN_WINDOW[0][0] >= 60.0:
                _TOKEN_WINDOW.popleft()
            used = sum(tok for _, tok in _TOKEN_WINDOW)
            if used < _MAX_TPM or not _TOKEN_WINDOW:
                return
            wait_s = max(0.2, min(5.0, 60.05 - (now - _TOKEN_WINDOW[0][0])))
        time.sleep(wait_s)


def _record_tpm(tokens):
    if _MAX_TPM > 0 and isinstance(tokens, int) and tokens > 0:
        with _TPM_LOCK:
            _TOKEN_WINDOW.append((time.monotonic(), tokens))


def text_content(content):
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    parts = []
    for item in content:
        if item.get('type') not in ('text', 'input_text', 'output_text'):
            raise ValueError(f"Unsupported content block: {item.get('type')}")
        parts.append(item['text'])
    return '\n'.join(parts)


def chat_request(body, protocol, model, cache):
    messages = []
    system = body.get('instructions') if protocol == 'responses' else body.get('system')
    if system:
        messages.append({'role': 'system', 'content': text_content(system)})

    def append(role, content='', calls=None):
        row = {'role': role, 'content': content}
        if calls:
            row['tool_calls'] = calls
            # Reasoning signatures/details must survive the native protocol projection.
            original = cache.get(calls[0]['id'], {})
            row.update({k: deepcopy(v) for k, v in original.items()
                        if k not in ('role', 'content', 'tool_calls') and v is not None})
        messages.append(row)

    if protocol == 'responses':
        items = body.get('input', [])
        if isinstance(items, str):
            items = [{'role': 'user', 'content': items}]
        for item in items:
            kind = item.get('type', 'message')
            if kind == 'message':
                append(item['role'], text_content(item.get('content')))
            elif kind == 'function_call':
                call = {'id': item['call_id'], 'type': 'function', 'function': {
                    'name': (item['namespace'] + '__' if item.get('namespace') else '') + item['name'], 'arguments': item['arguments']}}
                if messages and messages[-1]['role'] == 'assistant' and messages[-1].get('tool_calls'):
                    messages[-1]['tool_calls'].append(call)
                else:
                    append('assistant', None, [call])
            elif kind == 'function_call_output':
                messages.append({'role': 'tool', 'tool_call_id': item['call_id'],
                                 'content': text_content(item['output'])})
            elif kind != 'reasoning':
                raise ValueError(f'Unsupported Responses item: {kind}')
        if body.get('previous_response_id'):
            raise ValueError('Bridge requires explicit history, not previous_response_id')
        tools = []
        flattened = []
        for tool in body.get('tools', []):
            if tool.get('type') == 'namespace':
                flattened.extend({**t, 'name': tool['name'] + '__' + t['name'],
                    'description': tool.get('description', '') + '\n' + t.get('description', '')} for t in tool['tools'])
            else: flattened.append(tool)
        for tool in flattened:
            if tool.get('type') != 'function':
                raise ValueError('Bridge supports function tools only')
            tools.append({'type': 'function', 'function': {k: tool[k] for k in
                ('name', 'description', 'parameters', 'strict') if k in tool}})
    else:
        for item in body.get('messages', []):
            content = item['content']
            if isinstance(content, str):
                append(item['role'], content)
                continue
            chunks, calls = [], []
            for block in content:
                kind = block['type']
                if kind == 'text':
                    chunks.append(block['text'])
                elif kind == 'tool_use':
                    calls.append({'id': block['id'], 'type': 'function', 'function': {
                        'name': block['name'], 'arguments': json.dumps(block['input'])}})
                elif kind == 'tool_result':
                    if chunks:
                        append(item['role'], '\n'.join(chunks)); chunks = []
                    messages.append({'role': 'tool', 'tool_call_id': block['tool_use_id'],
                                     'content': text_content(block.get('content', ''))})
                elif kind not in ('thinking', 'redacted_thinking'):
                    raise ValueError(f'Unsupported Messages item: {kind}')
            if chunks or calls:
                append(item['role'], '\n'.join(chunks) or None, calls)
        tools = [{'type': 'function', 'function': {
            'name': tool['name'], 'description': tool.get('description', ''),
            'parameters': tool['input_schema']}} for tool in body.get('tools', [])]
    request = {'model': model, 'messages': messages, 'stream': False}
    if tools:
        request['tools'] = tools
    choice = body.get('tool_choice')
    if isinstance(choice, dict):
        if choice.get('type') in ('tool', 'function'):
            choice = {'type': 'function', 'function': {'name': choice['name']}}
        else:
            choice = {'any': 'required', 'auto': 'auto', 'none': 'none'}.get(choice.get('type'))
    if choice:
        request['tool_choice'] = choice
    for key in ('temperature', 'top_p', 'parallel_tool_calls'):
        if key in body:
            request[key] = body[key]
    limit = body.get('max_output_tokens', body.get('max_tokens'))
    if limit:
        request['max_tokens'] = limit
    effort = body.get('reasoning', {}).get('effort') if protocol == 'responses' else body.get('output_config', {}).get('effort')
    if effort and effort != 'none':
        request['reasoning_effort'] = effort
    return request


def _allowed_scalar_types(prop):
    if not isinstance(prop, dict):
        return set()
    types = set()
    raw = prop.get('type')
    if isinstance(raw, str):
        types.add(raw)
    elif isinstance(raw, list):
        types.update(t for t in raw if isinstance(t, str))
    for key in ('anyOf', 'oneOf'):
        for sub in prop.get(key) or ():
            if isinstance(sub, dict):
                types.update(_allowed_scalar_types(sub))
    return types


def coerce_tool_arguments(raw_arguments, parameters_schema):
    if not isinstance(raw_arguments, str) or not isinstance(parameters_schema, dict):
        return raw_arguments
    try:
        parsed = json.loads(raw_arguments)
    except (ValueError, TypeError):
        return raw_arguments
    if not isinstance(parsed, dict):
        return raw_arguments
    props = parameters_schema.get('properties')
    if not isinstance(props, dict):
        return raw_arguments
    changed = False
    for key, value in list(parsed.items()):
        if not isinstance(value, str) or key not in props:
            continue
        allowed = _allowed_scalar_types(props[key])
        if not allowed or 'string' in allowed:
            continue
        stripped = value.strip()
        if 'null' in allowed and stripped.lower() in ('null', 'none', ''):
            parsed[key] = None
            changed = True
        elif 'integer' in allowed and stripped.lstrip('-').isdigit() and stripped not in ('', '-'):
            parsed[key] = int(stripped)
            changed = True
        elif 'number' in allowed:
            try:
                parsed[key] = float(stripped)
                changed = True
            except ValueError:
                pass
        elif 'boolean' in allowed and stripped.lower() in ('true', 'false'):
            parsed[key] = stripped.lower() == 'true'
            changed = True
    return json.dumps(parsed) if changed else raw_arguments


def responses_reply(data, model, tool_schemas=None):
    choice = data['choices'][0]
    message = choice['message']
    output = []
    if message.get('content'):
        output.append({'id': 'msg_' + uuid.uuid4().hex, 'type': 'message',
                       'role': 'assistant', 'status': 'completed', 'content': [{
                           'type': 'output_text', 'text': text_content(message['content']), 'annotations': []}]})
    for call in message.get('tool_calls') or []:
        fn = dict(call['function'])
        if tool_schemas and fn.get('name') in tool_schemas:
            fn['arguments'] = coerce_tool_arguments(fn.get('arguments'), tool_schemas[fn['name']])
        output.append({'id': 'fc_' + uuid.uuid4().hex, 'type': 'function_call',
                       'status': 'completed', 'call_id': call['id'], **fn})
    usage = data.get('usage') or {}
    complete = choice.get('finish_reason') in ('stop', 'tool_calls')
    return {'id': 'resp_' + uuid.uuid4().hex, 'object': 'response', 'created_at': int(time.time()),
            'model': model, 'status': 'completed' if complete else 'incomplete', 'output': output,
            'error': None, 'incomplete_details': None if complete else {'reason': 'max_output_tokens'},
            'usage': {'input_tokens': usage.get('prompt_tokens', 0),
                      'output_tokens': usage.get('completion_tokens', 0),
                      'total_tokens': usage.get('total_tokens', 0),
                      'input_tokens_details': {'cached_tokens': usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)},
                      'output_tokens_details': {'reasoning_tokens': usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0)}}}


def response_events(response):
    initial = {**response, 'status': 'in_progress', 'output': [], 'usage': None}
    yield {'type': 'response.created', 'response': initial}
    yield {'type': 'response.in_progress', 'response': initial}
    for index, item in enumerate(response['output']):
        empty = {**item, 'status': 'in_progress'}
        empty['arguments' if item['type'] == 'function_call' else 'content'] = '' if item['type'] == 'function_call' else []
        yield {'type': 'response.output_item.added', 'output_index': index, 'item': empty}
        base = {'item_id': item['id'], 'output_index': index}
        if item['type'] == 'function_call':
            yield {'type': 'response.function_call_arguments.delta', **base, 'delta': item['arguments']}
            yield {'type': 'response.function_call_arguments.done', **base, 'arguments': item['arguments']}
        else:
            part = item['content'][0]
            yield {'type': 'response.content_part.added', **base, 'content_index': 0, 'part': {**part, 'text': ''}}
            yield {'type': 'response.output_text.delta', **base, 'content_index': 0, 'delta': part['text']}
            yield {'type': 'response.output_text.done', **base, 'content_index': 0, 'text': part['text']}
            yield {'type': 'response.content_part.done', **base, 'content_index': 0, 'part': part}
        yield {'type': 'response.output_item.done', 'output_index': index, 'item': item}
    yield {'type': 'response.' + response['status'], 'response': response}


def messages_reply(data, model, tool_schemas=None):
    choice = data['choices'][0]; message = choice['message']; content = []
    if message.get('content'):
        content.append({'type': 'text', 'text': text_content(message['content'])})
    for call in message.get('tool_calls') or []:
        name = call['function']['name']
        raw_args = call['function']['arguments']
        if tool_schemas and name in tool_schemas:
            raw_args = coerce_tool_arguments(raw_args, tool_schemas[name])
        content.append({'type': 'tool_use', 'id': call['id'], 'name': name,
                        'input': json.loads(raw_args)})
    usage = data.get('usage') or {}
    return {'id': 'msg_' + uuid.uuid4().hex, 'type': 'message', 'role': 'assistant',
            'model': model, 'content': content, 'stop_sequence': None,
            'stop_reason': {'stop': 'end_turn', 'tool_calls': 'tool_use', 'length': 'max_tokens'}.get(choice.get('finish_reason'), 'refusal'),
            'usage': {'input_tokens': usage.get('prompt_tokens', 0), 'output_tokens': usage.get('completion_tokens', 0)}}


def message_events(message):
    yield {'type': 'message_start', 'message': {**message, 'content': [], 'stop_reason': None,
                                               'usage': {**message['usage'], 'output_tokens': 0}}}
    for index, block in enumerate(message['content']):
        key = 'input' if block['type'] == 'tool_use' else 'text'
        yield {'type': 'content_block_start', 'index': index, 'content_block': {**block, key: {} if key == 'input' else ''}}
        delta = ({'type': 'input_json_delta', 'partial_json': json.dumps(block['input'])}
                 if key == 'input' else {'type': 'text_delta', 'text': block['text']})
        yield {'type': 'content_block_delta', 'index': index, 'delta': delta}
        yield {'type': 'content_block_stop', 'index': index}
    yield {'type': 'message_delta', 'delta': {'stop_reason': message['stop_reason'], 'stop_sequence': None}, 'usage': message['usage']}
    yield {'type': 'message_stop'}


class ChatBridge:
    def __init__(self, base, key, model, folder, *, served_model=None, timeout=300, on_response=None,
                 max_attempts=None, retry_backoff=2.0):
        self.upstream = api_base_url(base); self.key = key; self.model = model
        self.served_model = served_model or model; self.timeout = timeout
        self.max_attempts = max(1, int(max_attempts if max_attempts is not None
                                       else os.environ.get('SWARMHARM_BRIDGE_MAX_ATTEMPTS', '6')))
        self.retry_backoff = float(retry_backoff)
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32); self.cache = {}
        self.lock = threading.Lock(); self.cache_lock = threading.Lock(); self.sequence = 0
        bridge = self

        def capture(sequence, record):
            target = bridge.folder / f'{sequence:06d}.json.gz'
            temporary = target.with_suffix('.tmp')
            with gzip.open(temporary, 'wt') as output: json.dump(record, output)
            temporary.replace(target)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_json(self, status, value):
                data = json.dumps(value).encode()
                self.send_response(status); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

            def authorized(self):
                return (self.headers.get('Authorization') == 'Bearer ' + bridge.token
                        or self.headers.get('x-api-key') == bridge.token)

            def do_GET(self):
                if not self.authorized():
                    return self.send_json(401, {'error': {'message': 'Invalid local transport credential'}})
                if self.path.rstrip('/') == '/v1/models':
                    return self.send_json(200, {'object': 'list', 'data': [
                        {'id': bridge.model, 'object': 'model', 'context_window': 1_000_000}]})
                self.send_json(404, {'error': {'message': 'Unknown endpoint'}})

            def do_POST(self):
                if not self.authorized():
                    return self.send_json(401, {'error': {'message': 'Invalid local transport credential'}})
                endpoint = self.path.split('?')[0].rstrip('/')
                if endpoint not in ('/v1/responses', '/v1/messages'):
                    return self.send_json(400, {'error': {'message': 'Only text/function inference is supported'}})
                with bridge.lock:
                    bridge.sequence += 1; sequence = bridge.sequence
                record = {'at': time.time(), 'protocol': endpoint, 'upstream': bridge.upstream, 'version': VERSION}
                try:
                    body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    record['native_request'] = body
                    if body.get('model') != bridge.model:
                        raise ValueError('Native harness changed the registered model')
                    protocol = 'responses' if endpoint.endswith('responses') else 'messages'
                    with bridge.cache_lock:
                        cache_snapshot = dict(bridge.cache)
                    request = chat_request(body, protocol, bridge.served_model, cache_snapshot)
                    is_nvidia_byok = ('openrouter.ai' in bridge.upstream
                                      and str(bridge.served_model).lower().startswith(NVIDIA_BYOK_PREFIXES))
                    if 'tools' in request:
                        request['tools'] = _strip_unsupported_schema_keywords(
                            request['tools'], strip_strict=is_nvidia_byok)
                    if is_nvidia_byok:
                        request['provider'] = {'only': ['Nvidia']}
                    record['upstream_request'] = request
                    record['status'] = 'inflight'
                    capture(sequence, record)
                    payload_bytes = json.dumps(request).encode()
                    retries = []
                    data = None
                    for attempt in range(1, bridge.max_attempts + 1):
                        _pace_tpm()
                        req = urllib.request.Request(
                            bridge.upstream + '/chat/completions',
                            data=payload_bytes,
                            headers={'Content-Type': 'application/json',
                                     'Authorization': 'Bearer ' + bridge.key,
                                     'User-Agent': 'SwarmHarm-API/1.0'})
                        try:
                            with _UPSTREAM_SEMAPHORE:
                                with open_url(req, timeout=bridge.timeout) as upstream:
                                    data = json.load(upstream)
                                    record['response_headers'] = {k: v for k, v in upstream.headers.items()
                                        if k.lower() in ('x-request-id', 'request-id', 'x-axonhub-request-id')}
                            if isinstance(data, dict):
                                _record_tpm((data.get('usage') or {}).get('total_tokens'))
                            if isinstance(data, dict) and isinstance(data.get('error'), dict):
                                code = data['error'].get('code')
                                if code in NON_RETRYABLE_ERROR_CODES or attempt == bridge.max_attempts:
                                    raise ValueError('Upstream provider error: ' + json.dumps(data['error'])[:400])
                                delay = min(45.0, bridge.retry_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.5))
                                retries.append({'attempt': attempt, 'upstream_error_code': code, 'sleep_s': round(delay, 3)})
                                time.sleep(delay)
                                continue
                            if not isinstance(data, dict) or not isinstance(data.get('choices'), list) or not data['choices']:
                                if attempt == bridge.max_attempts:
                                    raise ValueError('Provider returned empty choices')
                                delay = min(45.0, bridge.retry_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.5))
                                retries.append({'attempt': attempt, 'error': 'empty_choices', 'sleep_s': round(delay, 3)})
                                time.sleep(delay)
                                continue
                            break
                        except urllib.error.HTTPError as error:
                            if error.code not in RETRYABLE_HTTP_STATUS or attempt == bridge.max_attempts:
                                raise
                            retry_after = None
                            if error.headers:
                                raw_ra = error.headers.get('Retry-After')
                                if raw_ra:
                                    try: retry_after = float(raw_ra)
                                    except ValueError: pass
                            base_delay = 12.0 if error.code == 429 else bridge.retry_backoff * (2 ** (attempt - 1))
                            delay = min(45.0, (retry_after + 1.0) if retry_after is not None
                                        else base_delay + random.uniform(0, 1.0))
                            retries.append({'attempt': attempt, 'status': error.code, 'sleep_s': round(delay, 3)})
                            try: error.close()
                            except Exception: pass
                            time.sleep(delay)
                        except (TimeoutError, urllib.error.URLError, http.client.IncompleteRead,
                                ConnectionError, json.JSONDecodeError) as error:
                            if attempt == bridge.max_attempts:
                                raise
                            delay = min(30.0, bridge.retry_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.4))
                            retries.append({'attempt': attempt, 'error': type(error).__name__, 'sleep_s': round(delay, 3)})
                            time.sleep(delay)
                    if retries:
                        record['retry_history'] = retries
                    record['upstream_response'] = data
                    canonical = lambda name: str(name).split('/')[-1].replace('.', '-')
                    if canonical(data.get('model')) not in {canonical(bridge.model), canonical(bridge.served_model)}:
                        raise ValueError('Provider returned a different model: ' + str(data.get('model')))
                    if on_response is not None:
                        on_response(data)
                    choice = data['choices'][0]
                    if choice.get('finish_reason') == 'content_filter':
                        raise ValueError('Provider returned content_filter')
                    if not isinstance((data.get('usage') or {}).get('total_tokens'), int):
                        raise ValueError('Provider must return usage.total_tokens')
                    with bridge.cache_lock:
                        for call in choice['message'].get('tool_calls') or []:
                            bridge.cache[call['id']] = deepcopy(choice['message'])
                    tool_schemas = {t['function']['name']: t['function'].get('parameters')
                                    for t in request.get('tools') or [] if 'function' in t}
                    value = (responses_reply(data, bridge.model, tool_schemas) if protocol == 'responses'
                             else messages_reply(data, bridge.model, tool_schemas))
                    if protocol == 'responses':
                        names = {t['name'] + '__' + child['name']: (t['name'], child['name'])
                            for t in body.get('tools', []) if t.get('type') == 'namespace' for child in t['tools']}
                        for item in value['output']:
                            if item.get('type') == 'function_call' and item['name'] in names:
                                item['namespace'], item['name'] = names[item['name']]
                    record['native_response'] = value
                    if not body.get('stream'):
                        return self.send_json(200, value)
                    self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Cache-Control', 'no-cache'); self.end_headers()
                    events = response_events(value) if protocol == 'responses' else message_events(value)
                    for index, event in enumerate(events):
                        if protocol == 'responses': event['sequence_number'] = index
                        self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
                    self.wfile.flush()
                except urllib.error.HTTPError as error:
                    raw = error.read().decode(errors='replace').replace(bridge.key, '[redacted]')
                    record['error'] = {'status': error.code, 'body': raw}
                    self.send_json(error.code, {'type': 'error', 'error': {'type': 'api_error', 'message': raw}})
                except Exception as error:
                    record['error'] = {'type': type(error).__name__, 'message': str(error).replace(bridge.key, '[redacted]')}
                    try: self.send_json(422, {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': record['error']['message']}})
                    except OSError: pass
                finally:
                    record['completed_at'] = time.time()
                    record['status'] = 'error' if record.get('error') else 'completed'
                    capture(sequence, record)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = False
        self.base = f'http://127.0.0.1:{self.server.server_port}/v1'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
