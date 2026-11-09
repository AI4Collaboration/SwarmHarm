"""Persistent Codex threads with controller-owned workstation tools."""

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import os
from hashlib import sha256
import signal
import json
from pathlib import Path
import queue
import shutil
import socket
import threading
import time

from codex_rpc import CodexRpc
from codex_evidence import mcp_output_text


NETWORK_ERROR_CODES = ('httpConnectionFailed', 'responseStreamDisconnected',
                       'responseStreamConnectionFailed')

# Frozen historical registrations included a controller-owned private registry.
# Current SwarmForm inputs omit it so the only cross-station business carrier is
# the deployment declared by the cell.  Keep both exact descriptions valid;
# accepting arbitrary roots would make the sealed workstation declaration
# meaningless.
REGISTERED_WORKSTATION_ROOTS = (
    ('/workspace', '/registry', '/var/tmp/exports', '/tmp', '/private/tmp'),
    ('/workspace', '/var/tmp/exports', '/tmp', '/private/tmp'),
)


def argument_value(raw):
    """Keep malformed native calls observable until the CLI reports its rejection."""
    try:
        return ('json', json.loads(raw))
    except (ValueError, TypeError):
        return ('raw', raw)


class CodexAgent:
    def __init__(self, actor, events, *, folder, model, thinking_level, tools,
                 active_tools, goal_mode, job_context=None, api_key=None,
                 api_base=None, registered_harness=None, request_timeout_ms=300000,
                 workstation_permissions=None, **unused):
        import codex_agent as runtime
        self.gateway = api_base is not None or api_key is not None
        if self.gateway:
            import codex_gateway as runtime
            if api_base != runtime.AXONHUB_BASE or not api_key:
                raise ValueError('Codex requires AxonHub base and host key')
        runtime.validate_model(model)
        if goal_mode not in (('off','codex_goal') if self.gateway else ('off',)):
            raise ValueError('Unsupported Codex goal mode')
        self.goal_mode = goal_mode
        self.goal_started = False
        self.goal_guard_parked = False
        self.goal_idle_turns = 0
        self.goal_tool_novel = False
        self.goal_tool_seen = set()
        self.first_native_turn = None
        self.pending_user_echo = None
        self.goal = None
        self.native_tools = runtime.native_tools(goal_mode) if self.gateway else runtime.NATIVE_TOOLS
        self.api_base, self.api_key = api_base, api_key
        self.workstation_permissions = deepcopy(workstation_permissions)
        if workstation_permissions is not None:
            if (not self.gateway or set(workstation_permissions) != {'type', 'networkAccess', 'writableRoots'}
                    or workstation_permissions.get('type') != 'workspaceWrite'
                    or not isinstance(workstation_permissions.get('networkAccess'), bool)
                    or tuple(workstation_permissions.get('writableRoots', ())) not in REGISTERED_WORKSTATION_ROOTS):
                raise ValueError('Unregistered workstation permission description')
        self.runtime, self.actor, self.events = runtime, actor, events
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.model, self.effort = model, thinking_level
        self.definitions = {tool['name']: tool for tool in tools}
        self.base_tools = list(active_tools)
        self.active_tools = list(active_tools)
        self.registered = registered_harness
        self.history = [{'role': 'system', 'content': json.dumps(runtime.SYSTEM_PROMPT)}]
        self.inputs, self.calls, self.replies = [], {}, {}
        self.output, self.outputs, self.sources = [], [], []
        self.turn, self.thread_id, self.native_turn = 0, None, None
        self.response_open, self.active, self.stopping = False, False, False
        self.failed = False
        self.timeout = request_timeout_ms / 1000
        self.last_progress, self.final_text = time.monotonic(), ''
        self.lock = threading.RLock()
        self.mcp_requests = 0
        self.call_ready = threading.Condition(self.lock)
        self.commands = queue.Queue()
        self.rpc = None
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    @contextmanager
    def record_guard(self):
        """Quiesce only this actor's child while updating its mediated record."""
        process = self.rpc.process if self.rpc is not None else None
        if process is None or process.poll() is not None:
            raise RuntimeError('Native record writer is unavailable')
        os.kill(process.pid, signal.SIGSTOP)
        try:
            deadline = time.monotonic() + 2
            while True:
                pid, status = os.waitpid(process.pid, os.WUNTRACED | os.WNOHANG)
                if pid:
                    if not os.WIFSTOPPED(status):
                        raise RuntimeError('Native record writer exited during capture')
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Native record writer did not quiesce')
                time.sleep(0.001)
            yield
        finally:
            try:
                os.kill(process.pid, signal.SIGCONT)
            except ProcessLookupError:
                pass

    def emit(self, kind, **values):
        self.events.put((self.actor, {'type': kind, **deepcopy(values)}))

    def _fatal(self, error):
        if self.failed or self.stopping:
            return
        self.failed = True
        self.emit('fatal', message=str(error))
        self.stopping = True
        for reply in list(self.replies.values()):
            reply.put({'aborted': True})
        self.commands.put(('close', None))

    def _tools(self):
        names = self.base_tools + self.native_tools + [
            name for name in self.active_tools if name not in self.base_tools]
        return [self.definitions[name] if name in self.definitions else {
            'type': 'function', 'name': name, 'description': 'Codex native auxiliary tool.',
            'parameters': {'type': 'object', 'properties': {}}} for name in names]

    def _write_tools(self):
        rows = [{'name': name, 'description': self.definitions[name]['description'],
                 'inputSchema': self.definitions[name]['parameters']}
                for name in self.active_tools]
        temporary = self.tool_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(rows))
        temporary.replace(self.tool_path)

    def _verify_tools(self):
        rows = self.rpc.request('mcpServerStatus/list', {})['data']
        if len(rows) != 1 or rows[0]['name'] != 'work' or set(rows[0]['tools']) != set(self.active_tools):
            raise RuntimeError('Codex MCP tools differ from the registered active tools')

    def _run(self):
        try:
            with ExitStack() as stack:
                identity = self.runtime.cli_identity()
                if self.registered and identity != self.registered['codex_cli']:
                    raise RuntimeError('Codex CLI differs from registration')
                self.home = stack.enter_context(self.runtime.isolated_home())
                import tempfile
                workspace = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='workspace-', dir='/tmp'))).resolve()
                catalog = self.runtime.native_catalog(self.home)
                if self.registered and self.runtime.digest(catalog) != self.registered['native_catalog_sha256']:
                    raise RuntimeError('Codex model catalog differs from registration')
                (self.folder / 'catalog.json').write_text(json.dumps(catalog))
                self.tool_path = self.home / 'tools.json'
                self._write_tools()
                endpoint = self.home / 'call.sock'
                self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.listener.bind(str(endpoint))
                self.listener.listen()
                self.listener.settimeout(0.2)
                stack.callback(self.listener.close)
                self.runtime.write_config(self.home, workspace, self.tool_path, endpoint,
                    self.model, self.effort, catalog)
                shutil.copy2(self.home / 'catalog.json', self.folder / 'tool-profile.json')
                shutil.copy2(self.home / 'config.toml', self.folder / 'config.toml')
                self.rpc = CodexRpc(self.runtime.command(self.goal_mode) if self.gateway else self.runtime.command(), env=(self.runtime.gateway_env(self.home, self.api_base, self.api_key) if self.gateway
                         else self.runtime.subscription_env(self.home)),
                    cwd=workspace, folder=self.folder, notification=self._notification,
                    server_request=self._server_request)
                stack.callback(self.rpc.close)
                self.runtime.initialize(self.rpc)
                if not self.gateway:
                    self.runtime.check_subscription(self.rpc)
                started = self.rpc.request('thread/start', {'model': self.model,
                    'cwd': str(workspace), 'approvalPolicy': 'never',
                    'sandbox': 'workspace-write' if self.workstation_permissions else 'read-only',
                    'experimentalRawEvents': True, 'ephemeral': False})
                self.thread_id = started['thread']['id']
                if started['model'] != self.model:
                    raise RuntimeError('Codex selected a different model')
                self._verify_tools()
                threading.Thread(target=self._accept, daemon=True).start()
                session_file=started['thread'].get('path')
                if self.gateway:
                    path=Path(session_file).resolve() if session_file else None
                    if (path is None or (self.home/'sessions').resolve() not in path.parents
                            or path.suffix!='.jsonl' or self.thread_id not in path.name):
                        raise RuntimeError('Codex returned an invalid native session path')
                    # Codex creates this registered path when the first turn begins.
                    session_file=str(path)
                self.emit('ready', session_file=session_file, cwd=str(workspace), active_tools=self.active_tools + self.native_tools,
                    system_prompt=self.runtime.SYSTEM_PROMPT, commands=[], session_id=self.thread_id)
                while True:
                    try:
                        command, value = self.commands.get(timeout=0.25)
                    except queue.Empty:
                        if self.active and time.monotonic() - self.last_progress > self.timeout:
                            raise TimeoutError('Codex native response completion timed out')
                        continue
                    if command == 'close':
                        break
                    if command == 'settle_goal':
                        if value.get('park'):
                            current = self.rpc.request('thread/goal/get', {'threadId': self.thread_id})['goal']
                            if current and current['status'] == 'active':
                                self.rpc.request('thread/goal/set', {'threadId': self.thread_id,
                                    'status': 'paused', 'origin': 'user'})
                                self.goal_guard_parked = True
                                self.rpc.record('controller', {'method': 'goal_progress_guard',
                                    'params': {'action': 'paused', 'idle_turns': self.goal_idle_turns}})
                        goal = self.rpc.request('thread/goal/get', {'threadId': self.thread_id})['goal']
                        with self.lock:
                            self.goal = goal
                            snapshot = {'goal': deepcopy(goal), 'source': 'codex-thread-goal'}
                            self.emit('settled', turn=value['turn'], text=value['text'],
                                error_message=None, aborted=False, native_goal=snapshot,
                                sdk_idle=not self.active, sdk_pending_messages=0)
                        continue
                    if self.active:
                        raise RuntimeError('Cannot change tools or submit another input during a Codex turn')
                    if command == 'tools':
                        if not set(value) <= self.definitions.keys():
                            raise ValueError('Unregistered Codex tool')
                        self.active_tools = value
                        self._write_tools()
                        self.rpc.request('config/mcpServer/reload', None)
                        self._verify_tools()
                    elif command == 'prompt':
                        text = '\n\n'.join(value)
                        resume_guard = self.goal_guard_parked
                        if resume_guard:
                            current = self.rpc.request('thread/goal/get', {'threadId': self.thread_id})['goal']
                            # A turn already in flight may have completed the goal after parking.
                            resume_guard = bool(current and current['status'] == 'paused')
                            self.goal_guard_parked = False
                        self.goal_idle_turns = 0
                        self.goal_tool_novel = False
                        with self.lock:
                            self.history.append({'role': 'user', 'content': text})
                            self.pending_user_echo = text
                            self.active = True
                            self.last_progress, self.final_text = time.monotonic(), ''
                        self.rpc.request('turn/start', {'threadId': self.thread_id,
                            'model': self.model, 'effort': self.effort,
                            **({'sandboxPolicy': self.workstation_permissions} if self.workstation_permissions else {}),
                            'input': [{'type': 'text', 'text': text, 'text_elements': []}]})
                        if resume_guard:
                            self.rpc.request('thread/goal/set', {'threadId': self.thread_id,
                                'status': 'active', 'origin': 'user'})
                            self.goal_guard_parked = False
                            self.rpc.record('controller', {'method': 'goal_progress_guard',
                                'params': {'action': 'resumed_new_business_input'}})
                        if self.goal_mode == 'codex_goal' and not self.goal_started:
                            self.goal_started = True
                            # Activate while the initial task turn is running. Codex
                            # owns subsequent continuation; no controller retry prompt.
                            self.rpc.request('thread/goal/set', {'threadId': self.thread_id,
                                'objective': value[-1], 'status':'active', 'origin':'user'})
                if self.active and self.native_turn:
                    self.rpc.request('turn/interrupt', {'threadId': self.thread_id, 'turnId': self.native_turn})
                snapshot = self.rpc.request('thread/read', {'threadId': self.thread_id, 'includeTurns': True})
                (self.folder / 'thread.json').write_text(json.dumps(snapshot))
                for path in (self.home / 'sessions').rglob('*.jsonl'):
                    if self.thread_id in path.name:
                        shutil.copy2(path, self.folder / 'session.jsonl')
                shutil.copytree(workspace, self.folder / 'workspace')
        except Exception as error:
            self._fatal(error)
        finally:
            self.stopping = True
            for reply in list(self.replies.values()):
                reply.put({'aborted': True})

    def _snapshot(self):
        return self.history + self.output + self.outputs

    def _begin(self, source):
        if self.response_open:
            return
        self.turn += 1
        self.response_open = True
        self.output, self.outputs, self.sources = [], [], []
        self.emit('request', turn=self.turn, attempt=1, payload={
            'record_kind': 'controller_projection', 'projection_source': 'codex-app-server',
            'count_scope': 'observed native response group', 'model': self.model,
            'reasoning': {'effort': self.effort}, 'input': self.history,
            'tools': self._tools(), 'system_prompt_config': self.runtime.SYSTEM_PROMPT,
            'session_id': self.thread_id, 'native_turn_id': self.native_turn,
            'native_record': source, 'native_input_records': self.inputs})

    def _response(self, source, completed=False, usage=None):
        value = {'record_kind': 'controller_projection', 'projection_source': 'codex-app-server',
            'id': f'{self.thread_id}:{self.turn}', 'model': self.model,
            'status': 'completed' if completed else 'in_progress', 'output': self.output,
            'native_record': source, 'native_output_records': self.sources,
            'session_id': self.thread_id, 'native_turn_id': self.native_turn}
        if usage:
            value['usage'] = {'input_tokens': usage.get('inputTokens'),
                'output_tokens': usage.get('outputTokens'),
                'input_tokens_details': {'cached_tokens': usage.get('cachedInputTokens')}}
        if completed:
            self.emit('provider_response', turn=self.turn, attempt=1,
                event={'type': 'response.completed', 'response': value}, history=self._snapshot())
        else:
            self.emit('response_update', turn=self.turn, attempt=1, response=value,
                history=self._snapshot())

    def _notification(self, message, source):
        with self.lock:
            try:
                method, params = message.get('method', ''), message.get('params') or {}
                if params.get('threadId') and self.thread_id and params['threadId'] != self.thread_id:
                    raise RuntimeError('Codex thread identity changed')
                if method == 'turn/started':
                    self.native_turn = params['turn']['id']
                    if self.first_native_turn is None:self.first_native_turn = self.native_turn
                    self.active = True
                    self.final_text = ''
                    self.last_progress = time.monotonic()
                elif method == 'thread/goal/updated':
                    self.goal = deepcopy(params['goal'])
                    self.emit('native_goal_state', turn=self.turn,
                        native_goal={'goal':self.goal,'source':'codex-thread-goal'})
                elif method == 'error':
                    error = params.get('error') or {}
                    info = error.get('codexErrorInfo')
                    code = next(iter(info), 'unspecified') if isinstance(info, dict) else info or 'unspecified'
                    recovering = (params.get('willRetry') is True
                                  and code in NETWORK_ERROR_CODES
                                  and error.get('misalignment') is None)
                    self.emit('native_transport_error', turn=self.turn,
                              code=code, will_retry=params.get('willRetry') is True,
                              recovering=recovering, native_record=source)
                    if not recovering:
                        raise RuntimeError(f'Codex error: {code} ({source})')
                    # Codex owns reconnection. Retain the in-flight turn, history
                    # and deadline; never send another prompt or replay tools.
                elif method in ('model/rerouted', 'thread/compacted', 'transport/error'):
                    raise RuntimeError('Codex stopped: ' + method)
                elif method == 'item/started' and params['item']['type'] == 'contextCompaction':
                    raise RuntimeError('Codex context compaction is outside the registered condition')
                elif method == 'rawResponseItem/completed':
                    item = deepcopy(params['item'])
                    kind = item.get('type')
                    if kind == 'message' and item.get('role') != 'assistant':
                        self.inputs.append(source)
                        if self.goal_mode == 'codex_goal' and item.get('role')=='user':
                            text='\n'.join(p.get('text','') for p in item.get('content',[]))
                            if text == self.pending_user_echo:
                                self.pending_user_echo = None
                            elif self.native_turn != self.first_native_turn:
                                self.history.append({'role':'user','content':text})
                        return
                    if kind == 'function_call_output':
                        if not self.response_open:
                            raise RuntimeError('Codex result arrived after its response boundary')
                        call = self.calls.get(item['call_id'])
                        if call and call['business']:
                            if 'output' not in call:
                                if call['claimed']:
                                    raise RuntimeError('Native Codex result has no completed controller execution')
                                call['rejected'] = True
                                self.emit('tool_result_error', turn=self.turn, call_id=item['call_id'],
                                    error=item['output'])
                            else:
                                if mcp_output_text(item['output']) != call['output']:
                                    raise RuntimeError('Codex truncated or changed a workstation result')
                                item['output'] = call['output']
                        if call and call['business']:
                            fingerprint = sha256(json.dumps([call['item']['name'],
                                argument_value(call['item']['arguments']), item['output']],
                                sort_keys=True).encode()).hexdigest()
                            if fingerprint not in self.goal_tool_seen:
                                self.goal_tool_seen.add(fingerprint)
                                self.goal_tool_novel = True
                        self.outputs.append(item)
                        self._response(source)
                        return
                    if kind not in ('message', 'function_call', 'reasoning'):
                        raise RuntimeError('Unregistered Codex output type: ' + str(kind))
                    self._begin(source)
                    if kind == 'function_call':
                        namespace = item.pop('namespace', None)
                        business = namespace == 'mcp__work'
                        if not business and item['name'].startswith('mcp__work__'):
                            item['name'] = item['name'][len('mcp__work__'):]
                            business = True
                        if (business and item['name'] not in self.active_tools) or (
                                not business and (namespace or item['name'] not in self.native_tools)):
                            raise RuntimeError('Unregistered Codex function call')
                        if item['call_id'] in self.calls:
                            raise RuntimeError('Duplicate Codex call ID')
                        self.calls[item['call_id']] = {'item': item, 'turn': self.turn,
                            'business': business, 'claimed': False}
                        self.call_ready.notify_all()
                    self.output.append(item)
                    if kind == 'message' and item.get('phase') in (None, 'final_answer'):
                        self.final_text += '\n'.join(part.get('text', '') for part in item['content'])
                    self.sources.append(source)
                    self._response(source)
                elif method == 'item/completed' and params['item']['type'] == 'mcpToolCall':
                    item = params['item']
                    call = self.calls.get(item['id'])
                    content = (item.get('result') or {}).get('content', [])
                    if call and not call['business']:
                        # Native resource discovery is rendered as mcpToolCall too;
                        # its result belongs to the CLI, not workstation execution.
                        if call['item']['name'] not in ('list_mcp_resources',
                                'list_mcp_resource_templates', 'read_mcp_resource'):
                            raise RuntimeError('Unexpected native MCP auxiliary completion')
                        return
                    if call and item['status'] == 'failed' and not call['claimed']:
                        return  # Native rejection before controller execution; keep its raw output.
                    if (not call or item['status'] != 'completed' or item['server'] != 'work'
                            or content != [{'type': 'text', 'text': call.get('output')}]
                            or item['tool'] != call['item']['name']
                            or item['arguments'] != json.loads(call['item']['arguments'])):
                        raise RuntimeError('Native Codex MCP delivery differs from controller execution')
                elif method == 'thread/tokenUsage/updated':
                    self.last_progress = time.monotonic()
                    self._begin(source)
                    self._response(source, True, (params.get('tokenUsage') or {}).get('last'))
                    self.history = self._snapshot()
                    calls = [item for item in self.output if item['type'] == 'function_call']
                    self.emit('turn_end', turn=self.turn, stop_reason='toolUse' if calls else 'stop',
                        tool_calls=calls, error_message=None)
                    self.output, self.outputs, self.sources = [], [], []
                    self.response_open = False
                elif method == 'turn/completed':
                    status = params['turn']['status']
                    if status != 'completed' or self.response_open:
                        raise RuntimeError('Codex turn did not complete: ' + status)
                    self.active = False
                    if self.goal_mode == 'codex_goal':
                        self.goal_idle_turns = 0 if self.goal_tool_novel else self.goal_idle_turns + 1
                        self.goal_tool_novel = False
                        self.commands.put(('settle_goal', {'turn':self.turn,'text':self.final_text,
                            'park': self.goal_idle_turns >= self.runtime.GOAL_PROGRESS_GUARD['consecutive_idle_turns']
                            and not self.goal_guard_parked}))
                    else:
                        self.emit('settled', turn=self.turn, text=self.final_text,
                            error_message=None, aborted=False)
            except Exception as error:
                self._fatal(error)

    def _server_request(self, message, source):
        params = message.get('params') or {}
        allowed = (message['method'] == 'mcpServer/elicitation/request'
            and params.get('serverName') == 'work' and params.get('threadId') == self.thread_id
            and params.get('_meta', {}).get('codex_approval_kind') == 'mcp_tool_call')
        if allowed:
            result = {'action': 'accept', 'content': {}}
        else:
            result = {'action': 'decline'}
            self._fatal('Unexpected Codex approval or elicitation request')
        self.rpc.send({'id': message['id'], 'result': result})

    def _accept(self):
        while not self.stopping:
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._call, args=(client,), daemon=True).start()

    def _match_call(self, params, timeout=5):
        """MCP execution and native event capture arrive on independent pipes."""
        meta = params.get('_meta') or {}
        identity = meta.get('callId')
        if meta.get('threadId', self.thread_id) != self.thread_id:
            raise RuntimeError('MCP execution belongs to a different native thread')
        deadline = time.monotonic() + timeout
        while True:
            if self.stopping:
                raise RuntimeError('Codex session stopped')
            candidates = [(key, call) for key, call in self.calls.items()
                if (identity is None or key == identity) and call['business']
                and not call['claimed'] and not call.get('rejected')
                and call['item']['name'] == params['name']
                and isinstance(params.get('arguments', {}), dict)
                and argument_value(call['item']['arguments']) == ('json', params.get('arguments', {}))]
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1 or identity in self.calls:
                raise RuntimeError('MCP execution differs from its native Codex call')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('MCP execution has no matching native Codex call')
            self.call_ready.wait(remaining)

    def _call(self, client):
        try:
            with client, client.makefile('rwb') as stream:
                params = json.loads(stream.readline())
                with self.lock:
                    self.mcp_requests += 1
                    capture = self.folder / 'mcp-requests'
                    capture.mkdir(exist_ok=True)
                    (capture / f'{self.mcp_requests:06d}.json').write_text(json.dumps(params))
                    if self.stopping:
                        raise RuntimeError('Codex session stopped')
                    identity, call = self._match_call(params)
                    call['claimed'] = True
                    reply = self.replies[identity] = queue.Queue()
                    self.emit('tool_call', id=identity, call_id=identity, name=params['name'],
                        arguments=params.get('arguments', {}), turn=call['turn'])
                result = reply.get(timeout=300)
                with self.lock:
                    if 'output' in result:
                        call['output'] = result['output']
                stream.write((json.dumps(result) + '\n').encode())
                stream.flush()
        except Exception as error:
            self._fatal(error)

    def prompt(self, *texts):
        self.commands.put(('prompt', list(texts)))

    def set_tools(self, tools):
        self.commands.put(('tools', list(tools)))

    def reply(self, request_id, **values):
        self.replies[request_id].put(values)

    def close(self, timeout=30):
        self.stopping = True
        for reply in list(self.replies.values()):
            reply.put({'aborted': True})
        self.commands.put(('close', None))
        self.worker.join(timeout=timeout)
        if self.worker.is_alive() and self.rpc:
            self.rpc.close()
            self.worker.join(timeout=5)
        return self.rpc.process.returncode if self.rpc else 1
