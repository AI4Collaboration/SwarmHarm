"""Three native sessions, real private arrivals and protected execution evidence.

Registration and source sealing are checked by the caller before this module runs.
By default only initial tasks and delivered private revisions start model turns.
Subclasses may enable a separately registered, evidence-bound continuation rule.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import threading
import time

from codex_agent import CodexAgent, wait_ready
from codex_gateway import AXONHUB_BASE
from response_monitor import classify
from swarmform.arrivals import IntakeSchedule
from swarmform.deployments import make_deployment
from swarmform.intake_observation import intake_read_receipts


BASH = {'type': 'function', 'name': 'bash',
        'description': 'Run a shell command on your persistent workstation. The working directory is /workspace. Commands have a 30-second limit; each output stream is limited to 64,000 bytes.',
        'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}},
                       'required': ['command'], 'additionalProperties': False}}


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def workspace_files(snapshot):
    return {path.removeprefix('/workspace/'): base64.b64decode(content).decode(errors='replace')
            for path, content in snapshot.get('/workspace', {}).items()
            if path.startswith('/workspace/releases/')}


class Collection:
    def __init__(self, root, registration, input_data, *, api_key,
                 agent_class=CodexAgent, deployment_class=None):
        self.root, self.reg, self.input = Path(root).resolve(), registration, input_data
        self.api_key, self.agent_class, self.deployment_class = api_key, agent_class, deployment_class
        self.actors = tuple(input_data['startup'])
        population = registration['population']
        allowed = (4, 8, 16, 32) if registration.get('study_mode') == 'swarmform-structure' else (3,)
        if (population not in allowed or len(self.actors) != population
                or registration['harness']['goal_mode'] != 'off'
                or set(input_data['prompts']) != set(self.actors)
                or set(input_data['private_arrivals']) != set(self.actors)):
            raise ValueError('Expected registered matched workstations and goal off')
        self.events = queue.Queue()
        self.agents, self.states, self.active = {}, {}, set()
        self.stopping = threading.Event()
        self.arrival_lock = threading.RLock()
        self.snapshot_lock = threading.Lock()
        self.snapshots, self.terminals, self.tool_counts, self.executed = {}, {}, {}, set()
        self.recorded_tools = set()
        self.sequence = 0
        self.read_receipts = {a: {} for a in self.actors}
        self.read_blobs = {a: set() for a in self.actors}
        self.pool = ThreadPoolExecutor(max_workers=population)
        self.jobs = {}
        self.failure, self.reason = None, 'quiescence'
        self.shutdown_errors = []
        self.schedule, self.arrival_thread = None, None

    def observation(self, actor, phase, value):
        with self.snapshot_lock:
            number = self.snapshots.get(actor, 0) + 1
            self.snapshots[actor] = number
            path = self.root / 'natural' / actor / 'observations' / f'{number:06d}.json'
            save(path, {'at': utc(), 'phase': phase, 'snapshot': value})
            if phase == 'terminal':
                self.terminals[actor] = path
            return str(path.relative_to(self.root))

    def record(self, actor, message):
        # Callbacks pass Futures only in an internal queue event, never in evidence.
        value = {k: v for k, v in message.items() if k != 'future'}
        with (self.root / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'at': utc(), 'controller_monotonic': time.monotonic(),
                                     'actor': actor, **value}, ensure_ascii=False) + '\n')

    def progress(self):
        save(self.root / 'progress.json', {'at': utc(), 'status': 'running',
            'active_agents': sorted(self.active), 'tools_inflight': len(self.jobs),
            'private_batches_delivered': len(self.schedule.receipts) if self.schedule else 0,
            'actors': self.states})

    def deliver_arrivals(self, deployment):
        try:
            while not self.stopping.is_set():
                # This thread may wait for an actor's command to finish. Other
                # sessions and their tool completions continue in the main loop.
                with self.arrival_lock:
                    receipts = self.schedule.deliver_due(time.monotonic(), deployment.deliver)
                    if receipts:
                        save(self.root / 'source-deliveries.json', list(self.schedule.receipts.values()))
                for receipt in receipts:
                    self.events.put((receipt['actor'], {'type': 'source_delivery', 'receipt': receipt}))
                if self.schedule.all_delivered:
                    return
                self.stopping.wait(.1)
        except BaseException as error:
            self.events.put((None, {'type': 'arrival_error', 'error': repr(error)}))

    def notify_ready(self):
        # Do not hold the event loop behind an ongoing private delivery. An
        # undelivered file cannot produce a prompt, even if its due time passed.
        if not self.arrival_lock.acquire(blocking=False):
            return
        try:
            for actor in self.actors:
                for receipt in self.schedule.acknowledge_reads(actor, self.read_receipts[actor]):
                    self.record(actor, {'type': 'intake_notice_suppressed', **receipt})
                    save(self.root / 'natural' / actor / 'intake-read-receipts.json',
                         [row for (owner, _), row in self.schedule.accessed.items() if owner == actor])
                notice = self.schedule.pending_notice(actor, active=actor in self.active)
                if notice:
                    self.agents[actor].prompt(notice['text'])
                    self.schedule.acknowledge_notice(notice)
                    self.active.add(actor)
                    self.states[actor]['notices'].append({**notice, 'at': utc()})
                    self.record(actor, {'type': 'business_notice', **notice})
                    save(self.root / 'natural' / actor / 'notices.json', self.states[actor]['notices'])
        finally:
            self.arrival_lock.release()

    def start_continuation(self, deployment):
        """Optional registered continuation; legacy collections have none."""

    def observe_tool_result(self, actor, result, snapshot):
        """Observe delivered tool work before the model can finish its turn."""

    def observe_tool_timing(self, actor, call, snapshot):
        """Optional observer-only timing; also receives undelivered completed work."""

    def quiescence_ready(self):
        return True

    def deadline_reason(self):
        return 'wall_budget'

    def close_continuation(self):
        pass

    def shutdown_failure(self, stage, error, *, actor=None):
        """Keep the first cause and separately retain every cleanup failure."""
        value = {'type': stage, 'error_type': type(error).__name__,
                 'message': repr(error), 'at': utc()}
        if actor is not None:
            value['actor'] = actor
        self.shutdown_errors.append(value)
        if self.failure is None:
            self.failure, self.reason = value, 'runtime_failure'
            save(self.root / 'failure.json', self.failure)

    def finish_tool(self, actor, message, result, *, delivered):
        turn = message['turn']
        key = actor, turn
        number = self.tool_counts.get(key, 0) + 1
        self.tool_counts[key] = number
        self.sequence += 1
        record = {'event_id': self.sequence, 'call_id': message['call_id'].split('|', 1)[0],
                  'name': message['name'], 'arguments': message['raw_arguments'],
                  'result': result, 'finished_at': utc()}
        suffix = '' if delivered else '-undelivered'
        save(self.root / 'natural' / actor / 'trace' / f'{turn:04d}-tool-{number}{suffix}.json', record)
        self.recorded_tools.add((actor, message['call_id']))
        self.states[actor]['tools'] += 1
        if delivered:
            self.agents[actor].reply(message['id'], output=json.dumps(result, ensure_ascii=False))

    def execute_tool(self, deployment, actor, command, submitted):
        started = time.monotonic()
        result, snapshot = deployment.execute(actor, command)
        snapshot['controller_tool_timing'] = {'submitted': submitted, 'worker_started': started,
                                              'worker_finished': time.monotonic()}
        return result, snapshot

    def handle(self, actor, message, deployment):
        self.record(actor, message)
        kind, turn = message['type'], message.get('turn', 0)
        trace = self.root / 'natural' / actor / 'trace' if actor else None
        if kind == 'request':
            save(trace / f'{turn:04d}.request.json', message['payload'])
        elif kind in ('response_update', 'provider_response'):
            value = message['response'] if kind == 'response_update' else message['event']['response']
            save(trace / f'{turn:04d}.response.json', value)
            save(trace.parent / 'history.json', message['history'])
            if kind == 'provider_response':
                classification = classify(value)
                save(trace / f'{turn:04d}.response-review.json', classification)
                if classification['status'] in ('provider_filter', 'native_refusal'):
                    raise RuntimeError(classification['status'])
        elif kind == 'tool_call':
            identity = actor, message['call_id']
            if identity in self.executed:
                raise RuntimeError('Repeated native tool call identity')
            self.executed.add(identity)
            response = json.loads((trace / f'{turn:04d}.response.json').read_text())
            calls = [c for c in response.get('output', []) if c.get('type') == 'function_call'
                     and c.get('call_id') == message['call_id'].split('|', 1)[0]]
            if (len(calls) != 1 or calls[0]['name'] != message['name']
                    or json.loads(calls[0]['arguments']) != message['arguments']):
                raise RuntimeError('Execution arguments differ from the native call')
            message = {**message, 'raw_arguments': calls[0]['arguments']}
            args = message['arguments']
            if (message['name'] != 'bash' or not isinstance(args, dict) or set(args) != {'command'}
                    or not isinstance(args['command'], str)):
                self.finish_tool(actor, message, {'error': 'Expected bash arguments with exactly one string field: command.'}, delivered=True)
            elif len(args['command'].encode()) > 140000:
                self.finish_tool(actor, message, {'error': 'Shell command exceeds 140,000 UTF-8 bytes.'}, delivered=True)
            else:
                save(trace / f'{turn:04d}-command-{len(self.executed):06d}-start.json',
                     {'at': utc(), 'call_id': message['call_id'], 'arguments': args})
                future = self.pool.submit(self.execute_tool, deployment, actor, args['command'], time.monotonic())
                self.jobs[future] = actor, message
                future.add_done_callback(lambda done: self.events.put((None, {'type': 'shell_ready', 'future': done})))
        elif kind == 'shell_ready':
            future = message['future']
            owner, call = self.jobs[future]
            result, snapshot = future.result()
            if 'controller_tool_timing' in snapshot:
                snapshot['controller_tool_timing']['collector_received'] = time.monotonic()
            self.observe_tool_timing(owner, call, snapshot)
            if reference := snapshot.get('command_observation'):
                expected = {'/workspace/' + path: content.encode()
                    for files in self.input['private_arrivals'][owner].values() for path, content in files.items()}
                reads = intake_read_receipts(reference, expected, self.read_blobs[owner])
                for path, receipt in reads.items():
                    receipt['observation'] = str(Path(receipt['observation']).relative_to(self.root))
                    self.read_receipts[owner].setdefault(path, receipt)
            self.observe_tool_result(owner, result, snapshot)
            # Observation may fail after execution succeeded. Until it finishes,
            # keep the job available for shutdown's undelivered-result capture.
            self.finish_tool(owner, call, result, delivered=True)
            self.jobs.pop(future)
        elif kind == 'settled':
            if message.get('aborted') or message.get('error_message'):
                raise RuntimeError('Native session did not settle normally: ' + str(message))
            self.active.discard(actor)
            self.states[actor].update(final=message.get('text', ''), last_settled_turn=turn)
        elif kind in ('fatal', 'exited', 'arrival_error'):
            raise RuntimeError(str(message))
        elif kind == 'turn_end' and message.get('stop_reason') == 'aborted':
            raise RuntimeError('Native turn aborted')

    def retain_pending_commands(self):
        """Capture completed execution without delivering new work during close."""
        self.pool.shutdown(wait=True)
        for future, (actor, call) in list(self.jobs.items()):
            try:
                result, snapshot = future.result()
                self.observe_tool_timing(actor, call, snapshot)
                if (actor, call['call_id']) not in self.recorded_tools:
                    self.finish_tool(actor, call, result, delivered=False)
            except BaseException as error:
                save(self.root / 'natural' / actor / 'command-error.json', {'error': repr(error)})
                self.shutdown_failure('CommandShutdown', error, actor=actor)
            finally:
                self.jobs.pop(future)

    def drain_terminal_events(self, deployment):
        """Keep late evidence and failures; never execute queued tool calls."""
        while True:
            try:
                actor, message = self.events.get_nowait()
            except queue.Empty:
                return
            if message['type'] in ('request', 'response_update', 'provider_response'):
                try:
                    self.handle(actor, message, deployment)
                except Exception as error:
                    self.shutdown_failure('ProjectionShutdown', error, actor=actor)
            else:
                self.record(actor, message)
                if message['type'] in ('fatal', 'exited', 'arrival_error'):
                    self.shutdown_failure('TerminalEvent', RuntimeError(str(message)), actor=actor)

    def run(self):
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / 'started.json').exists():
            raise FileExistsError('This registration has already been collected')
        # Exclusive creation prevents a second invocation from crossing the start.
        with (self.root / 'started.json').open('x') as stream:
            json.dump({'at': utc(), 'population': len(self.actors)}, stream)
        began = time.monotonic()
        deadline = began + self.reg['budget']['max_batch_seconds']
        deployment = None
        try:
            options = dict(observation_sink=self.observation,
                observation_archive=self.root / 'read-observations')
            deployment = (self.deployment_class(self.input['startup'],
                shared=self.reg['deployment']['shared'], **options) if self.deployment_class
                else make_deployment(self.input['startup'], self.reg, **options))
            save(self.root / 'bindings.json', deployment.bindings)
            for actor in self.actors:
                folder = self.root / 'natural' / actor
                self.states[actor] = {'status': 'starting', 'tools': 0, 'notices': [], 'final': ''}
                self.agents[actor] = self.agent_class(actor, self.events, folder=folder / 'codex',
                    model=self.reg['model'], thinking_level=self.reg['reasoning'],
                    tools=self.input['tools'], active_tools=[t['name'] for t in self.input['tools']],
                    goal_mode='off', api_key=self.api_key, api_base=AXONHUB_BASE,
                    registered_harness=self.reg['harness'],
                    workstation_permissions=self.reg.get('workstation_permissions'),
                    response_idle_timeout_ms=(self.reg['budget'].get('response_idle_timeout_seconds') or 0) * 1000 or None,
                    request_timeout_ms=self.reg['budget']['request_timeout_seconds'] * 1000)
            ready = wait_ready(self.events, self.actors)
            for actor, value in ready.items():
                expected = {t['name'] for t in self.input['tools']} | set(self.reg['harness']['extension_tools'])
                if set(value['active_tools']) != expected:
                    raise RuntimeError('Native tools differ from registration')
                deployment.stations[actor].bind_native_cwd(value['cwd'])
                self.states[actor].update(codex_session=value, status='running')
            activated = time.monotonic()
            self.schedule = IntakeSchedule(self.input['private_arrivals'], self.reg['arrival_offsets'], activated_at=activated)
            self.schedule.deliver_due(activated, deployment.deliver)
            save(self.root / 'source-deliveries.json', list(self.schedule.receipts.values()))
            save(self.root / 'activation.json', {'at': utc(), 'monotonic': activated,
                'all_sessions_ready': True, 'actors': list(self.actors)})
            deadline = min(deadline, activated + self.reg['budget']['max_agent_seconds'])
            self.activated_at = activated
            self.deadline = deadline
            self.start_continuation(deployment)
            for actor in self.actors:
                save(self.root / 'natural' / actor / 'initial-input.json', {
                    'texts': self.input['prompts'][actor], 'tools': self.input['tools']})
                self.agents[actor].prompt(*self.input['prompts'][actor])
                self.active.add(actor)
            self.arrival_thread = threading.Thread(target=self.deliver_arrivals, args=(deployment,), daemon=True)
            self.arrival_thread.start()
            while time.monotonic() < self.deadline:
                self.notify_ready()
                notifications_complete = self.schedule.updates_accounted
                if (self.schedule.all_delivered and notifications_complete
                        and not self.arrival_thread.is_alive()
                        and not self.active and not self.jobs and self.events.empty()
                        and self.quiescence_ready()):
                    break
                try:
                    actor, message = self.events.get(timeout=.1)
                except queue.Empty:
                    continue
                self.handle(actor, message, deployment)
                self.progress()
            else:
                self.reason = self.deadline_reason()
        except BaseException as error:
            self.failure = {'type': type(error).__name__, 'message': str(error), 'at': utc()}
            self.reason = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'runtime_failure'
            save(self.root / 'failure.json', self.failure)
        finally:
            self.stopping.set()
            try:
                self.close_continuation()
            except BaseException as error:
                self.shutdown_failure('ContinuationShutdown', error)
            if self.arrival_thread:
                self.arrival_thread.join(timeout=120)
                if self.arrival_thread.is_alive():
                    self.shutdown_failure('ArrivalShutdown', RuntimeError('Private writer did not stop'))
            self.retain_pending_commands()
            with ThreadPoolExecutor(max_workers=len(self.actors)) as pool:
                closes = {actor: pool.submit(agent.close) for actor, agent in self.agents.items()}
                for actor, future in closes.items():
                    try:
                        self.states[actor]['native_exit_code'] = future.result()
                    except BaseException as error:
                        self.shutdown_failure('NativeShutdown', error, actor=actor)
            self.drain_terminal_events(deployment)
            if deployment:
                try:
                    deployment.close()
                except BaseException as error:
                    self.shutdown_failure('DeploymentShutdown', error)
            service_terminal = getattr(deployment, 'terminal_service', None)
            if service_terminal is not None:
                save(self.root / 'service-terminal.json', service_terminal)
            for actor, state in self.states.items():
                state['status'] = self.reason
                save(self.root / 'natural' / actor / 'result.json', state)
            save(self.root / 'terminal-snapshots.json', {a: str(p.relative_to(self.root)) for a, p in self.terminals.items()})
            completion = {'at': utc(), 'reason': self.reason, 'failure': self.failure,
                'shutdown_errors': self.shutdown_errors,
                'elapsed_seconds': time.monotonic() - began, 'actors': self.states,
                'terminal_snapshot_count': len(self.terminals),
                'service_terminal': 'service-terminal.json' if service_terminal is not None else None,
                'behavior_review': 'pending'}
            save(self.root / 'completion.json', completion)
            save(self.root / 'progress.json', {'status': 'closed', **completion})
        return completion
