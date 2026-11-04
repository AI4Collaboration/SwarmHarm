"""Direct AxonHub Responses transport. No agent SDK, preset or hidden calls."""
from copy import deepcopy
import json
from pathlib import Path
import queue
from queue import Empty
import threading
import urllib.error
import urllib.request
from guardrails import open_url

API_BASE = 'https://lmportal.iefbr14.xyz/v1'
PUBLIC_HEADERS = {'User-Agent': 'swarmharm-direct-api/1.0',
                  'Accept': 'application/json', 'Content-Type': 'application/json'}


def registration(goal_mode='off', model=None):
    if goal_mode != 'off':
        raise ValueError('Direct API execution has no harness goal extension')
    value = {'kind': 'direct-api', 'authentication': 'axonhub', 'gateway': API_BASE,
            'api': 'openai-responses', 'http_headers': deepcopy(PUBLIC_HEADERS),
            'installed': {}, 'context_window': None,
            'system_prompt': None, 'builtin_tools': [], 'extension_tools': [],
            'goal_mode': 'off', 'settings': {'retry': {'maxRetries': 0}},
            'native_binding': 'exact-http-json-v1',
            'input_delivery': 'explicit-history-v1',
            'natural_prompt_contract_covers_all_subject_input': True}
    if model and model.startswith('anthropic/'):
        value['assistant_output_order'] = 'text-before-tool-calls-v1'
    return value


def output_history_items(output, *, group_tool_calls=False):
    """Keep one assistant turn together for the gateway's Messages conversion.

    Raw provider output is saved unchanged. Moving non-call items before calls
    prevents a trailing assistant text item from becoming a prefill after tool
    results. No content is dropped and relative tool-call order is unchanged.
    """
    items = deepcopy(output)
    if group_tool_calls:
        items.sort(key=lambda item: item.get('type') == 'function_call')
    return items


def new_queue():
    return queue.Queue()


def wait_ready(events, actors, timeout=120):
    ready = {}
    while len(ready) < len(actors):
        actor, message = events.get(timeout=timeout)
        if message['type'] != 'ready' or actor in ready:
            raise RuntimeError('Unexpected direct transport startup event')
        ready[actor] = message
    return ready


class DirectAgent:
    """Exchange registered messages and executed tool returns with one model.

    The existing collector owns business state, execution, notices and budgets.
    This transport adds no instruction text and never retries model requests.
    """
    def __init__(self, actor, events, *, folder, model, api_base, api_key,
                 thinking_level, max_output_tokens, context_window,
                 request_timeout_ms, tools, active_tools, job_context=None,
                 goal_mode='off'):
        contract = registration(goal_mode, model)
        self.group_tool_calls = contract.get('assistant_output_order') == 'text-before-tool-calls-v1'
        if api_base.rstrip('/') != API_BASE or not api_key:
            raise ValueError('Direct model calls require AxonHub and a host key')
        self.actor, self.events = actor, events
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.model, self.key = model, api_key
        self.effort, self.max_tokens = thinking_level, max_output_tokens
        self.timeout = request_timeout_ms / 1000
        self.tools = {t['name']: deepcopy(t) for t in tools}
        self.active = list(active_tools)
        if set(self.active) - self.tools.keys():
            raise ValueError('Unknown active tools')
        self.history = ([{'role': 'system', 'content': job_context}]
                        if job_context else [])
        self.inputs, self.results = queue.Queue(), queue.Queue()
        self.closed = threading.Event()
        self.turn = 0
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()
        self._emit(type='ready', system_prompt=job_context,
                   active_tools=self.active, commands=[])

    def _emit(self, **message):
        self.events.put((self.actor, message))

    def prompt(self, *texts):
        if texts:
            self.inputs.put('\n\n'.join(texts))

    def set_tools(self, names):
        if set(names) - self.tools.keys():
            raise ValueError('Unregistered tool')
        self.active = list(names)

    def reply(self, request_id, *, output):
        self.results.put((request_id, output))

    def _post(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(API_BASE + '/responses', data=body,
            headers={'Authorization': 'Bearer ' + self.key, **PUBLIC_HEADERS}, method='POST')
        with open_url(request, timeout=self.timeout) as response:
            raw = response.read()
        (self.folder / f'{self.turn:04d}.response-body.json').write_bytes(raw)
        return json.loads(raw)

    def _drain_inputs(self):
        while not self.inputs.empty():
            text = self.inputs.get_nowait()
            if text is not None:
                self.history.append({'role': 'user', 'content': text})

    def _run(self):
        try:
            while not self.closed.is_set():
                text = self.inputs.get()
                if text is None:
                    return
                self.history.append({'role': 'user', 'content': text})
                while not self.closed.is_set():
                    self._drain_inputs()
                    self.turn += 1
                    payload = {'model': self.model, 'input': deepcopy(self.history),
                        'tools': [deepcopy(self.tools[n]) for n in self.active],
                        'reasoning': {'effort': self.effort},
                        'max_output_tokens': self.max_tokens, 'store': False,
                        'stream': False, 'include': ['reasoning.encrypted_content']}
                    (self.folder / f'{self.turn:04d}.request-body.json').write_text(
                        json.dumps(payload, ensure_ascii=False))
                    self._emit(type='request', turn=self.turn, attempt=1, payload=payload)
                    try:
                        response = self._post(payload)
                    except Exception as error:
                        if isinstance(error, urllib.error.HTTPError):
                            (self.folder / f'{self.turn:04d}.error-body.json').write_bytes(error.read())
                        self._emit(type='provider_response', turn=self.turn, attempt=1,
                            event={'type': 'response.failed', 'response': {
                                'status': 'failed', 'model': self.model, 'output': [],
                                'error': {'code': type(error).__name__,
                                          'http_status': getattr(error, 'code', None)}}})
                        raise
                    if response.get('model') != self.model:
                        raise ValueError('Gateway returned a different model')
                    if response.get('status') != 'completed':
                        self._emit(type='provider_response', turn=self.turn, attempt=1,
                                   event={'type': 'response.failed', 'response': response})
                        raise ValueError('Model response did not complete')
                    self._emit(type='provider_response', turn=self.turn, attempt=1,
                               event={'type': 'response.completed', 'response': response})
                    output = response.get('output', [])
                    self.history.extend(output_history_items(output, group_tool_calls=self.group_tool_calls))
                    calls = [v for v in output if v.get('type') == 'function_call']
                    text = '\n'.join(b['text'] for v in output if v.get('type') == 'message'
                                     for b in v.get('content', []) if b.get('type') == 'output_text')
                    for call in calls:
                        if call['name'] not in self.active:
                            raise ValueError('Model requested an unavailable tool')
                        request_id = f'{self.turn}:{call["call_id"]}'
                        self._emit(type='tool_call', id=request_id, turn=self.turn,
                                   call_id=call['call_id'], name=call['name'])
                        result_id, result = self.results.get()
                        if self.closed.is_set():
                            return
                        if result_id != request_id:
                            raise ValueError('Tool result belongs to another request')
                        self.history.append({'type': 'function_call_output',
                                             'call_id': call['call_id'], 'output': result})
                    self._emit(type='turn_end', turn=self.turn, stop_reason='toolUse' if calls else 'stop',
                               tool_calls=len(calls), error_message=None, text=text,
                               response_id=response['id'])
                    if not calls:
                        self._emit(type='settled', turn=self.turn, text=text,
                                   aborted=False, error_message=None)
                        break
        except Exception as error:
            # Avoid logging request headers or exception representations containing credentials.
            self._emit(type='fatal', message=f'Direct API request failed ({type(error).__name__})')

    def close(self, timeout=30):
        self.closed.set()
        self.inputs.put(None)
        self.results.put((None, None))
        self.worker.join(timeout=timeout)
        return 0 if not self.worker.is_alive() else 1
