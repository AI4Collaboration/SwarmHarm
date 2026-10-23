"""Durable SSE collection. Never retries or supplies a lost response."""
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'back-office-v1'))
from durability import append, atomic_bytes
from run_model import Chat, TOOLS, UNRESOLVED


def fold(frames):
    output = {}; message = {'role': 'assistant', 'content': None}; calls = {}; reasoning = {}; finish = None; done = False
    for line in frames:
        if not line.startswith('data:'): continue
        data = line[5:].strip()
        if data == '[DONE]': done = True; continue
        chunk = json.loads(data)
        if chunk.get('error'): raise ValueError('stream returned an error')
        for key in ('id', 'model', 'provider', 'usage', 'created', 'object'):
            if chunk.get(key) is not None: output[key] = chunk[key]
        for choice in chunk.get('choices', []):
            if choice.get('index', 0) != 0: raise ValueError('multiple choices are unsupported')
            delta = choice.get('delta') or {}
            for key in ('content', 'reasoning'):
                if delta.get(key) is not None: message[key] = (message.get(key) or '') + delta[key]
            for call in delta.get('tool_calls') or []:
                target = calls.setdefault(call['index'], {'type': 'function', 'function': {'name': '', 'arguments': ''}})
                if call.get('id'):
                    if target.get('id') and target['id'] != call['id']: raise ValueError('tool identity changed')
                    target['id'] = call['id']
                for key in ('name', 'arguments'):
                    if (call.get('function') or {}).get(key) is not None:
                        target['function'][key] += call['function'][key]
            for detail in delta.get('reasoning_details') or []:
                index = detail.get('index', 0)
                target = reasoning.setdefault(index, {})
                for key, value in detail.items():
                    if key in ('text', 'data', 'signature') and isinstance(value, str): target[key] = target.get(key, '') + value
                    elif value is not None:
                        if key in target and target[key] != value: raise ValueError('reasoning identity changed')
                        target[key] = value
            if choice.get('finish_reason') is not None: finish = choice['finish_reason']
    if not done or finish is None or not output.get('id'): raise ValueError('incomplete stream')
    if calls:
        if any(not c.get('id') or not c['function']['name'] for c in calls.values()): raise ValueError('incomplete tool call')
        message['tool_calls'] = [calls[i] for i in sorted(calls)]
    if reasoning: message['reasoning_details'] = [reasoning[i] for i in sorted(reasoning)]
    output['choices'] = [{'index': 0, 'message': message, 'finish_reason': finish}]
    return output


class DurableChat(Chat):
    def __call__(self, messages):
        request_id = uuid.uuid4().hex
        session = 'v3:' + self.journal.parent.parent.parent.name + ':' + self.journal.parent.name
        body = dict(self.body, messages=messages, tools=TOOLS, stream=True,
                    stream_options={'include_usage': True}, user=request_id, session_id=session)
        append(self.journal, {'kind': 'request_prepared', 'request_id': request_id, 'url': self.url,
                             'body': body, 'time': time.time(), 'protocol': 'sse-fold-v1'})
        request = urllib.request.Request(self.url, json.dumps(body).encode(),
                  {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key})
        started = time.monotonic(); frames = []
        stream_path = self.journal.parent / 'responses' / (request_id + '.stream.jsonl')
        try:
            timeout = min(self.timeout, max(.1, getattr(self, 'deadline', float('inf')) - time.monotonic()))
            with urllib.request.urlopen(request, timeout=timeout) as response:
                headers = {key: response.headers[key] for key in ('x-request-id', 'request-id', 'x-generation-id') if key in response.headers}
                append(self.journal, {'kind': 'response_headers', 'request_id': request_id,
                                      'headers': headers, 'status': response.status, 'time': time.time()})
                if 'text/event-stream' not in response.headers.get('Content-Type', ''): raise ValueError('expected SSE response')
                seen_id = None
                for raw in response:
                    line = raw.decode('utf-8').rstrip('\r\n')
                    append(stream_path, {'line': line, 'time': time.time()})
                    frames.append(line)
                    if time.monotonic() > getattr(self, 'deadline', float('inf')): raise TimeoutError('wave deadline reached')
                    if line.startswith('data:') and line[5:].strip() != '[DONE]':
                        data = json.loads(line[5:].strip())
                        if data.get('id') and data['id'] != seen_id:
                            seen_id = data['id']
                            append(self.journal, {'kind': 'stream_identity', 'request_id': request_id,
                                                 'provider_generation_id': seen_id, 'model': data.get('model'), 'provider': data.get('provider')})
                output = fold(frames)
        except urllib.error.HTTPError as error:
            atomic_bytes(self.journal.parent / 'responses' / (request_id + '.error'), error.read())
            kind = 'request_rejected' if error.code in (400, 401, 403, 404, 422) else 'request_unknown'
            append(self.journal, {'kind': kind, 'request_id': request_id, 'http_status': error.code})
            raise RuntimeError('HTTP ' + str(error.code) + '; no retry') from error
        except Exception as error:
            append(self.journal, {'kind': 'request_unknown', 'request_id': request_id, 'error': type(error).__name__, 'partial_stream': str(stream_path)})
            raise RuntimeError('Incomplete request ' + request_id + '; preserved; no retry') from error
        path = self.journal.parent / 'responses' / (request_id + '.json')
        atomic_bytes(path, json.dumps(output).encode())
        append(self.journal, {'kind': 'response_saved', 'request_id': request_id, 'path': str(path),
                             'stream_path': str(stream_path), 'assembly': 'sse-fold-v1'})
        provider = (output.get('provider') or '').lower().replace(' ', '')
        pin = self.body['provider']['order'][0].split('/')[0].lower().replace(' ', '')
        if output.get('model') != self.body['model'] or provider != pin:
            UNRESOLVED.set(); raise RuntimeError('Served identity mismatch; response preserved')
        choice = output['choices'][0]; usage = output.get('usage') or {}
        metadata = {'id': output['id'], 'model': output['model'], 'provider': output['provider'],
                    'finish_reason': choice['finish_reason'], 'usage': usage, 'cost': usage.get('cost'),
                    'latency_s': time.monotonic() - started, 'transport': 'sse-fold-v1'}
        return choice['message'], metadata
