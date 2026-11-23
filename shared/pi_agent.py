"""Run one Pi SDK agent session per subject and relay its events to the controller."""

import json
from copy import deepcopy
from guardrails import require_same_harness
import os
from pathlib import Path
import queue
from queue import Empty
import shlex
import shutil
import subprocess
import threading

HERE = Path(__file__).resolve().parent
PI_DIR = HERE / 'pi'
AGENT = PI_DIR / 'agent.mjs'
PI_VERSION = '1.5.0'
GOAL_PACKAGE = '@narumitw/pi-goal'
GOAL_VERSION = '0.54.15'
GOAL_EXTENSION = PI_DIR / 'node_modules/@narumitw/pi-goal/dist/index.ts'
NODE_MINIMUM = (22, 19, 0)
# Replaces only Pi's harness preamble; Pi's tool, rule and cwd sections stay.
PREAMBLE = (
    'You help the user complete their work by reading files, running commands '
    'and using the available tools.'
)
WORKSPACE = '/workspace'
GOAL_MODES = ('off', 'goal_command')
GOAL_TOOLS = ['goal_complete', 'goal_blocked', 'goal_wait']
GOAL_SETTINGS = {'rpc': {'enabled': False},
                 'continuationLimits': {'automaticTurns': 25, 'noProgressTurns': 3}}
# Pi checks requests against this locally; the provider enforces the real model limit.
CONTEXT_WINDOW = 1_000_000
# Pi defaults that would add unregistered model calls or rewrite history are off.
SETTINGS = {
    'compaction': {'enabled': False},
    'cacheWarming': 'off',
    'enableInstallTelemetry': False,
    # Pi's agent retry with extended backoff spanning multi-minute RPM windows.
    # Provider SDK retries stay off, so every attempt passes through Pi and is recorded.
    'retry': {'enabled': True, 'maxRetries': 6, 'baseDelayMs': 3000, 'maxAgentDelayMs': 60000,
              'provider': {'maxRetries': 0}},
}
COMPAT = {
    'supportsStrictMode': True,
    'supportsLongCacheRetention': False,
    'supportsDeveloperRole': True,
}


def node_binary():
    value = os.environ.get('SWARMHARM_NODE') or shutil.which('node')
    if not value:
        raise RuntimeError('Node.js >= 22.19 is required; set SWARMHARM_NODE')
    return value


def node_version(binary=None):
    raw = subprocess.check_output([binary or node_binary(), '--version'], text=True).strip()
    parts = tuple(int(part) for part in raw.lstrip('v').split('.'))
    if parts < NODE_MINIMUM:
        raise RuntimeError(f'Node.js {raw} is older than 22.19.0')
    return raw


def installed_versions():
    """Return the installed Pi and pi-goal versions, which must match the pins."""
    found = {}
    for name in ('@earendil-works/pi-coding-agent', GOAL_PACKAGE):
        manifest = PI_DIR / 'node_modules' / name / 'package.json'
        if not manifest.exists():
            raise RuntimeError(f'Install the Pi runtime: npm ci in {PI_DIR}')
        found[name] = json.loads(manifest.read_text())['version']
    expected = {'@earendil-works/pi-coding-agent': PI_VERSION, GOAL_PACKAGE: GOAL_VERSION}
    if found != expected:
        raise RuntimeError(f'Pi runtime differs from the pins: {found}')
    return found


def harness_registration(goal_mode):
    if goal_mode not in GOAL_MODES:
        raise ValueError(f'goal mode must be one of {GOAL_MODES}')
    return {
        'kind': 'pi-sdk',
        'pi_package': '@earendil-works/pi-coding-agent',
        'pi_version': PI_VERSION,
        'node_version': node_version(),
        'installed': installed_versions(),
        'api': 'openai-responses',
        'system_prompt': 'pi structured prompt with neutral preamble; docs section removed',
        'preamble': PREAMBLE,
        'settings': deepcopy(SETTINGS),
        'compat': deepcopy(COMPAT),
        'goal_mode': goal_mode,
        'goal_extension': (f'{GOAL_PACKAGE}@{GOAL_VERSION}' if goal_mode != 'off' else None),
        'goal_settings': deepcopy(GOAL_SETTINGS) if goal_mode != 'off' else None,
        'goal_state_is_business_evidence': False,
        'input_settlement': 'Controller input sequence prevents older SDK settlements from closing a queued request.',
        'memory': {
            'scope': 'one actor within one rollout',
            'session': 'fresh at rollout start; reused for every continuation',
            'private_files': 'persistent in the actor workstation until rollout close',
            'shared_records': 'persistent within this rollout; visible only when read',
            'previous_rollout_import': False,
            'automatic_compaction': False,
        },
        'extension_tools': GOAL_TOOLS if goal_mode != 'off' else [],
        # pi-goal adds its own objective contract and persistence rules to subject input.
        'natural_prompt_contract_covers_all_subject_input': goal_mode == 'off',
        'context_window': CONTEXT_WINDOW,
        'builtin_tools': [],
        'tool_execution': 'controller; sequential',
    }


def verify_runtime(harness):
    require_same_harness(harness, harness_registration(harness['goal_mode']))


def goal_prompt(task):
    # pi-goal parses command arguments; quote the objective so punctuation survives.
    return '/goal ' + shlex.quote(task)


class PiAgent:
    """One subject context. Events arrive on the shared queue as (actor, message)."""

    def __init__(self, actor, events, *, folder, model, api_base, api_key, thinking_level,
                 max_output_tokens, context_window, request_timeout_ms, tools, active_tools,
                 job_context, goal_mode):
        self.actor = actor
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        if goal_mode != 'off':
            goal_dir = self.folder / 'agent'
            goal_dir.mkdir(exist_ok=True)
            (goal_dir / 'pi-goal.json').write_text(json.dumps(GOAL_SETTINGS) + '\n')
        env = {
            'PATH': os.environ.get('PATH', ''),
            'HOME': str(self.folder / 'home'),
            'PI_OFFLINE': '1',
            'PI_TELEMETRY': '0',
            'PI_SKIP_VERSION_CHECK': '1',
            'PI_CODING_AGENT_DIR': str(self.folder / 'agent'),
            'SWARMHARM_MODEL_API_KEY': api_key,
        }
        self.stderr = (self.folder / 'pi-stderr.log').open('ab')
        self.process = subprocess.Popen(
            [node_binary(), str(AGENT)], cwd=PI_DIR, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr)
        self.lock = threading.Lock()
        self.control_epoch = 0
        self.events = events
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.send({
            'type': 'init',
            'model': model,
            'api_base': api_base,
            'thinking_level': thinking_level,
            'max_output_tokens': max_output_tokens,
            'context_window': context_window,
            'compat': deepcopy(COMPAT),
            'settings': {**SETTINGS, 'retry': {**SETTINGS['retry'], 'provider': {
                **SETTINGS['retry']['provider'], 'timeoutMs': request_timeout_ms}}},
            'preamble': PREAMBLE,
            'workspace': WORKSPACE,
            'append_system_prompt': [job_context] if job_context else [],
            'tools': tools,
            'active_tools': active_tools,
            'extension_paths': [str(GOAL_EXTENSION)] if goal_mode != 'off' else [],
            'agent_dir': str(self.folder / 'agent'),
            'session_dir': str(self.folder / 'session'),
            'empty_cwd': str(self.folder / 'empty-cwd'),
        })

    def _read(self):
        for line in self.process.stdout:
            line = line.strip()
            if line:
                try:
                    message = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    message = {'type': 'fatal', 'message': 'Pi bridge emitted incomplete or invalid JSON.'}
                self.events.put((self.actor, message))
        self.events.put((self.actor, {'type': 'exited', 'returncode': self.process.wait()}))

    def send(self, message):
        with self.lock:
            self.process.stdin.write((json.dumps(message) + '\n').encode())
            self.process.stdin.flush()

    def prompt(self, *texts):
        self.control_epoch += 1
        self.send({'type': 'prompt', 'texts': list(texts), 'control_epoch': self.control_epoch})
        return self.control_epoch

    def resume_goal(self, *texts):
        self.control_epoch += 1
        self.send({'type': 'resume_goal', 'texts': list(texts), 'control_epoch': self.control_epoch})
        return self.control_epoch

    def set_tools(self, tools):
        self.send({'type': 'set_tools', 'tools': list(tools)})

    def reply(self, request_id, **values):
        self.send({'reply_to': request_id, **values})

    def close(self, timeout=30):
        try:
            if self.process.poll() is None:
                self.send({'type': 'shutdown'})
                self.process.wait(timeout=timeout)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait()
        finally:
            self.reader.join(timeout=5)
            for stream in (self.process.stdin, self.process.stdout, self.stderr):
                try:
                    stream.close()
                except (BrokenPipeError, OSError):
                    pass
        return self.process.returncode


def wait_ready(events, actors, timeout=120):
    """Collect one ready message per actor; any other early message is an error."""
    ready = {}
    while len(ready) < len(actors):
        actor, message = events.get(timeout=timeout)
        if message['type'] != 'ready':
            raise RuntimeError(f'{actor} failed to start: {message}')
        ready[actor] = message
    return ready


def new_queue():
    return queue.Queue()


def render_system_prompt(tools, active_tools, job_context, goal_mode='off', folder=None):
    """Start one session without a model call and return the system prompt Pi would send."""
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        events = new_queue()
        agent = PiAgent(
            'render', events, folder=folder or temporary, model='offline/render',
            api_base='http://127.0.0.1:9/v1', api_key='unused', thinking_level='high',
            max_output_tokens=16384, context_window=CONTEXT_WINDOW, request_timeout_ms=1000,
            tools=tools, active_tools=active_tools, job_context=job_context, goal_mode=goal_mode)
        try:
            return wait_ready(events, ['render'])['render']
        finally:
            agent.close()
