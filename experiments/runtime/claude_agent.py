"""Claude Code sessions authenticated with the operator's Claude subscription."""

from hashlib import sha256
import json
import os
from pathlib import Path
import queue
from queue import Empty
import re
import shutil
import subprocess
import tempfile
import threading

HERE = Path(__file__).resolve().parent
CLAUDE_DIR = HERE / 'claude'
AGENT = CLAUDE_DIR / 'agent.mjs'
SDK_VERSION = '0.3.312'
GOAL_MODES = ('off', 'claude_goal')
SYSTEM_PROMPT = {'type': 'preset', 'preset': 'claude_code'}
CONTEXT_WINDOW = None  # The subscription CLI owns the actual model context limit.
CONFLICTING_ENV = {
    'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL',
    'ANTHROPIC_CUSTOM_HEADERS', 'CLAUDE_CODE_USE_BEDROCK',
    'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY',
}
SETTINGS = {
    'tools': [], 'settingSources': [], 'strictMcpConfig': True,
    'permissionMode': 'default', 'persistSession': True,
}
RUNTIME_ENV = {
    'DISABLE_AUTOUPDATER': '1',
    'DISABLE_COMPACT': '1', 'DISABLE_AUTO_COMPACT': '1',
    'CLAUDE_CODE_MAX_RETRIES': '0',
    'CLAUDE_CODE_GOAL_CHECKIN_MINUTES': '0',
}
EVIDENCE_LIMIT = (
    'Native evidence is the Claude Agent SDK message stream and Claude Code session files. '
    'Controller request/response records are projections, not captured provider HTTP payloads. '
    'SDK-internal prompts, transport retries and full model-visible context are not observable.'
)


def node_binary():
    value = os.environ.get('SWARMHARM_NODE') or shutil.which('node')
    if not value:
        raise RuntimeError('Node.js >= 22.19 is required; set SWARMHARM_NODE')
    return value


def node_version():
    raw = subprocess.check_output([node_binary(), '--version'], text=True).strip()
    if tuple(map(int, raw.lstrip('v').split('.'))) < (22, 19, 0):
        raise RuntimeError('Node.js >= 22.19 is required')
    return raw


def claude_binary():
    value = os.environ.get('SWARMHARM_CLAUDE') or shutil.which('claude')
    if not value or not Path(value).is_file():
        raise RuntimeError('Install Claude Code and sign in with claude auth login')
    return str(Path(value).resolve())


def subscription_env():
    """Never inherit API billing, proxy routing or arbitrary Claude configuration."""
    conflicts = sorted(name for name in CONFLICTING_ENV if os.environ.get(name))
    if conflicts:
        raise RuntimeError('Subscription harness requires unsetting: ' + ', '.join(conflicts))
    env = {name: os.environ[name] for name in (
        'PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR', 'LANG', 'LC_ALL',
        'CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_OAUTH_TOKEN',
    ) if name in os.environ}
    env.update(RUNTIME_ENV)
    return env


def subscription_auth():
    """Read only an allowlist of auth-status fields; never save accounts or tokens."""
    result = subprocess.run(
        [claude_binary(), '--setting-sources', '', 'auth', 'status'],
        env=subscription_env(), capture_output=True, text=True, timeout=30)
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('Claude auth status did not return JSON; update Claude Code') from None
    if (result.returncode or value.get('loggedIn') is not True
            or value.get('authMethod') not in ('claude.ai', 'oauth_token')
            or value.get('apiProvider') != 'firstParty'):
        raise RuntimeError('Claude subscription login required; run claude auth login (without --console)')
    plan = value.get('subscriptionType')
    if plan is not None and plan not in ('pro', 'max', 'team', 'enterprise'):
        raise RuntimeError('Claude auth status does not report an eligible subscription')
    return {'logged_in': True, 'auth_method': value['authMethod'],
            'api_provider': 'firstParty', 'subscription_type': plan}


def installed_versions():
    manifest = CLAUDE_DIR / 'node_modules/@anthropic-ai/claude-agent-sdk/package.json'
    if not manifest.exists():
        raise RuntimeError(f'Install the Claude runtime: npm ci in {CLAUDE_DIR}')
    version = json.loads(manifest.read_text())['version']
    if version != SDK_VERSION:
        raise RuntimeError(f'Claude Agent SDK differs from the pin: {version}')
    return {'@anthropic-ai/claude-agent-sdk': version}


def cli_identity():
    binary = claude_binary()
    version = subprocess.check_output([binary, '--version'], env=subscription_env(), text=True).strip()
    match = re.match(r'(\d+)\.(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (2, 1, 304):
        raise RuntimeError('Claude Code >= 2.1.304 is required')
    return {'version': version, 'sha256': sha256(Path(binary).read_bytes()).hexdigest()}


def validate_model(model):
    if not re.fullmatch(r'claude-(?=.*\d)[a-z0-9]+(?:[.-][a-z0-9]+)*', model) or model.endswith('-latest'):
        raise ValueError('Use an explicit Claude model ID such as claude-sonnet-4-6; aliases and provider prefixes are not accepted')


def subscription_catalog(model,effort):
    """Inspect the authenticated SDK catalog; no user prompt or model call."""
    validate_model(model)
    with tempfile.TemporaryDirectory(prefix='swarmharm-subscription-catalog-') as folder:
        result=subprocess.run([node_binary(),str(CLAUDE_DIR/'catalog.mjs'),model,effort,claude_binary()],
            cwd=folder,env=subscription_env(),capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError('Claude subscription model catalog check failed')
    value=json.loads(result.stdout)
    if not value.get('model_and_effort_found'):
        raise RuntimeError(f'The subscription CLI catalog does not expose {model} at {effort} effort')
    return value


def harness_registration(goal_mode='off', model=None):
    if goal_mode not in GOAL_MODES:
        raise ValueError('pi-goal is available only with the Pi harness; use claude_goal for Claude')
    if goal_mode != 'off' and model is None:
        raise ValueError('Claude native goals require an exact evaluator model')
    if model is not None:validate_model(model)
    auth = subscription_auth()
    environment = dict(RUNTIME_ENV)
    if model is not None:environment['ANTHROPIC_DEFAULT_HAIKU_MODEL'] = model
    return {
        'kind': 'claude-code', 'authentication': 'claude-subscription',
        'auth_status': auth, 'installed': installed_versions(),
        'node_version': node_version(), 'claude_code': cli_identity(),
        'settings': SETTINGS, 'environment': environment, 'system_prompt': SYSTEM_PROMPT,
        'working_directory': {
            'kind': 'private temporary directory outside rollout evidence',
            'archive': 'workspace/ after SDK shutdown',
            'business_tools': 'execute in the offline workstation',
        },
        'goal_mode': goal_mode, 'extension_tools': [], 'builtin_tools': [],
        'platform_notice_delivery': {
            'native_role': 'user', 'content_source': 'platform_status JSON',
            'developer_role_supported': False,
        },
        'goal_evaluator': ({'model': model, 'reasoning_effort': 'SDK-managed; not exposed',
            'implementation': 'Claude Code native /goal prompt-based Stop hook',
            'evidence_limit': 'Evaluator calls and complete inputs are not exposed in the SDK stream; native goal status and session records are retained.'}
            if goal_mode == 'claude_goal' else None),
        'natural_prompt_contract_covers_all_subject_input': False,
        'context_window': CONTEXT_WINDOW,
        'tool_execution': 'controller; sequential; SDK MCP tools only',
        'evidence_limit': EVIDENCE_LIMIT, 'live_validation': 'live rollout pending',
    }


def verify_runtime(harness):
    subscription_auth()
    if installed_versions() != harness['installed']:
        raise RuntimeError('Installed Claude Agent SDK differs from registration')
    if node_version() != harness['node_version'] or cli_identity() != harness['claude_code']:
        raise RuntimeError('Node.js or Claude Code differs from registration; prepare a fresh rollout')


class ClaudeAgent:
    """Same controller protocol as Pi, with native SDK evidence kept separately."""

    def __init__(self, actor, events, *, folder, model, thinking_level,
                 max_output_tokens, request_timeout_ms, tools, active_tools,
                 goal_mode, **unused):
        validate_model(model)
        if goal_mode not in GOAL_MODES:
            raise ValueError('Claude Code does not load pi-goal; use claude_goal')
        self.actor = actor
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        env = subscription_env()
        # Native /goal normally uses a small model. Keep the registered model
        # fixed for that evaluator as well, without any alternative routing.
        env['ANTHROPIC_DEFAULT_HAIKU_MODEL'] = model
        env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'] = str(max_output_tokens)
        env['API_TIMEOUT_MS'] = str(request_timeout_ms)
        self.stderr = (self.folder / 'claude-stderr.log').open('ab')
        self.process = subprocess.Popen(
            [node_binary(), str(AGENT)], cwd=CLAUDE_DIR, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            start_new_session=True)
        self.lock = threading.Lock()
        self.events = events
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.send({
            'type': 'init', 'model': model, 'effort': thinking_level,
            'claude_binary': claude_binary(), 'folder': str(self.folder),
            'tools': tools,
            'active_tools': active_tools, 'settings': SETTINGS,
            'request_timeout_ms': request_timeout_ms,
            'goal_mode': goal_mode,
        })

    def _read(self):
        try:
            for line in self.process.stdout:
                if line.strip():
                    self.events.put((self.actor, json.loads(line)))
        except (ValueError, OSError):
            self.events.put((self.actor, {'type': 'fatal', 'message': 'Invalid Claude bridge output'}))
        self.events.put((self.actor, {'type': 'exited', 'returncode': self.process.wait()}))

    def send(self, message):
        with self.lock:
            self.process.stdin.write((json.dumps(message) + '\n').encode())
            self.process.stdin.flush()

    def prompt(self, *texts):
        self.send({'type': 'prompt', 'texts': list(texts)})

    def set_tools(self, tools):
        self.send({'type': 'set_tools', 'tools': list(tools)})

    def reply(self, request_id, **values):
        self.send({'reply_to': request_id, **values})

    def close(self, timeout=30):
        import signal
        try:
            if self.process.poll() is None:
                self.send({'type': 'shutdown'})
                self.process.wait(timeout=timeout)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            try:os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:pass
            self.process.wait()
        finally:
            self.reader.join(timeout=5)
            for stream in (self.process.stdin, self.process.stdout, self.stderr):
                stream.close()
        return self.process.returncode


def new_queue():
    return queue.Queue()


def wait_ready(events, actors, timeout=120):
    ready = {}
    while len(ready) < len(actors):
        actor, message = events.get(timeout=timeout)
        if message['type'] != 'ready':
            raise RuntimeError(f'{actor} failed to start: {message}')
        ready[actor] = message
    return ready
