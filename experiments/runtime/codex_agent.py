"""Offline compatibility adapter for historical Codex app-server evidence."""

from contextlib import contextmanager
import base64
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import sys

from codex_rpc import CodexRpc

CLI_VERSION = '0.141.0'
HERE = Path(__file__).resolve().parent
SYSTEM_PROMPT = {'type': 'native', 'source': 'Codex CLI model catalog',
                 'replacement': False, 'append': False}
GOAL_MODES = ('off',)
NATIVE_TOOLS = ['list_mcp_resources', 'list_mcp_resource_templates',
                'read_mcp_resource', 'update_plan', 'view_image']
DISABLED_FEATURES = ('apps', 'plugins', 'browser_use', 'computer_use',
    'image_generation', 'multi_agent', 'tool_suggest', 'workspace_dependencies',
    'shell_tool', 'unified_exec', 'goals', 'hooks', 'shell_snapshot', 'memories')
CONFLICTING_ENV = {
    'OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_API_BASE',
    'CODEX_AUTH_JSON', 'OPENAI_ORG_ID', 'OPENAI_PROJECT_ID',
}
EVIDENCE_LIMIT = (
    'Native evidence is the Codex app-server JSON-RPC stream and stored thread items. '
    'Controller projections are not provider HTTP payloads or complete provider context. '
    'Per-response provider model IDs and hidden transport retries are unexposed. '
    'Catalog membership does not prove inference entitlement.'
)


def codex_binary():
    # Keep the experiment pin alongside a user's normal Codex installation.
    # The desktop app may update its bundled CLI independently, so a generic
    # `codex` lookup is only the final fallback.
    path = (os.environ.get('SWARMHARM_CODEX')
            or shutil.which(f'codex-{CLI_VERSION}')
            or shutil.which('codex'))
    if not path or not Path(path).is_file():
        raise RuntimeError('Historical offline Codex fixture requires its pinned CLI; live runs use codex_gateway')
    return str(Path(path).resolve())


def cli_identity():
    binary = codex_binary()
    version = subprocess.check_output([binary, '--version'], text=True).strip()
    if version != f'codex-cli {CLI_VERSION}':
        raise RuntimeError(f'Codex CLI must match the pin {CLI_VERSION}; found {version}')
    return {'version': version, 'sha256': sha256(Path(binary).read_bytes()).hexdigest()}


def subscription_env(home):
    conflicts = sorted(key for key in CONFLICTING_ENV if os.environ.get(key))
    if conflicts:
        raise RuntimeError('Codex subscription harness requires unsetting: ' + ', '.join(conflicts))
    env = {key: os.environ[key] for key in (
        'PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR', 'LANG', 'LC_ALL',
    ) if key in os.environ}
    env['CODEX_HOME'] = str(home)
    env['HOME'] = str(home)
    return env


@contextmanager
def isolated_home(minimum_validity_seconds=90 * 60):
    """Use a bounded access-token snapshot; retain refresh credentials only on the host."""
    source = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'auth.json'
    try:
        auth = json.loads(source.read_text())
    except (OSError, ValueError):
        raise RuntimeError('Codex ChatGPT login required; run codex login') from None
    if (auth.get('auth_mode') != 'chatgpt' or auth.get('OPENAI_API_KEY')
            or not isinstance(auth.get('tokens'), dict)
            or not auth['tokens'].get('access_token')):
        raise RuntimeError('Codex harness requires ChatGPT subscription auth, not API-key auth')
    try:
        payload = auth['tokens']['access_token'].split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        expires = claims['exp']
        refreshed = datetime.fromisoformat(auth['last_refresh'].replace('Z', '+00:00'))
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError('Codex login has no verifiable access-token lifetime') from None
    if (expires - time.time() < minimum_validity_seconds
            or (datetime.now(timezone.utc) - refreshed).total_seconds() > 7 * 86400):
        raise RuntimeError('Refresh the Codex ChatGPT login before starting a registered rollout')
    auth = deepcopy(auth)
    # Concurrent subjects cannot rotate or invalidate the operator's refresh token.
    # An unexpected 401 is preserved as an auth failure; it never changes billing.
    auth['tokens']['refresh_token'] = ''
    with tempfile.TemporaryDirectory(prefix='codex-home-', dir='/tmp') as folder:
        home = Path(folder)
        home.chmod(0o700)
        path = home / 'auth.json'
        with open(path, 'x', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            json.dump(auth, stream)
        yield home


def validate_model(model):
    if (not re.fullmatch(r'[a-z0-9][a-z0-9.-]*', model)
            or model in ('auto', 'default', 'latest') or model.endswith('-latest')):
        raise ValueError('Use an explicit model ID from the Codex catalog, without provider prefixes')


def initialize(connection):
    result = connection.request('initialize', {
        'clientInfo': {'name': 'swarmharm', 'title': 'SwarmHarm', 'version': '1.0'},
        'capabilities': {'experimentalApi': True},
    })
    connection.send({'method': 'initialized', 'params': {}})
    return result


def command():
    return [codex_binary(), *[arg for feature in DISABLED_FEATURES
            for arg in ('--disable', feature)], 'app-server', '--listen', 'stdio://']


def native_catalog(home):
    return json.loads(subprocess.check_output([codex_binary(), 'debug', 'models'],
        env=subscription_env(home), cwd=home, text=True, timeout=60))


def catalog_profile(catalog):
    """Change tool capabilities only; leave every native instruction field intact."""
    value = deepcopy(catalog)
    for row in value['models']:
        row['apply_patch_tool_type'] = None
        row['input_modalities'] = ['text']
        row['supports_parallel_tool_calls'] = False
    return value


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_config(home, workspace, definitions, endpoint, model, effort, catalog):
    (home / 'catalog.json').write_text(json.dumps(catalog_profile(catalog)))
    # No inherited host config, project instructions, custom provider or prompt override.
    config = [f'model={json.dumps(model)}', 'model_provider="openai"',
        f'model_reasoning_effort={json.dumps(effort)}', 'forced_login_method="chatgpt"',
        'cli_auth_credentials_store="file"', 'project_doc_max_bytes=0',
        'web_search="disabled"', 'model_auto_compact_token_limit=2147483647',
        'model_catalog_json=' + json.dumps(str(home / 'catalog.json')),
        '[mcp_servers.work]', 'required=true', 'tool_timeout_sec=300',
        'command=' + json.dumps(sys.executable),
        'args=' + json.dumps([str(HERE / 'codex_mcp.py'), str(definitions), str(endpoint)]),
        '[tools.experimental_request_user_input]', 'enabled=false']
    (home / 'config.toml').write_text('\n'.join(config) + '\n')


def check_subscription(connection):
    result = connection.request('account/read', {'refreshToken': False}, private=True)
    account = result.get('account') or {}
    if account.get('type') != 'chatgpt':
        raise RuntimeError('Codex app-server requires ChatGPT subscription authentication')
    return {'authentication': 'chatgpt-subscription',
            'subscription_type': account.get('planType')}


def harness_registration(goal_mode='off', model=None):
    if goal_mode != 'off':
        raise ValueError('Codex harness currently supports goal mode off only')
    validate_model(model or '')
    identity = cli_identity()
    with isolated_home() as home:
        catalog = native_catalog(home)
    return {'kind': 'codex', 'authentication': 'chatgpt-subscription',
        'installed': {'codex-cli': CLI_VERSION}, 'codex_cli': identity,
        'native_catalog_sha256': digest(catalog),
        'tool_profile': {'input_modalities': ['text'], 'apply_patch_tool_type': None,
                         'supports_parallel_tool_calls': False},
        'disabled_features': list(DISABLED_FEATURES), 'goal_mode': 'off',
        'system_prompt': SYSTEM_PROMPT, 'extension_tools': NATIVE_TOOLS,
        'builtin_tools': NATIVE_TOOLS, 'context_window': None,
        'output_token_limit': 'Codex CLI managed; no per-response override',
        'request_timeout_scope': 'native response completion, including workstation execution',
        'tool_execution': 'controller MCP tools in offline workstations; native auxiliary tools retained',
        'authentication_snapshot': 'access token only; minimum 90 minutes validity; no refresh credential',
        'request_count_scope': 'observed native response groups; starts and failed calls without output unobservable',
        'natural_prompt_contract_covers_all_subject_input': False,
        'evidence_limit': EVIDENCE_LIMIT, 'live_validation': 'live rollout pending'}


def verify_runtime(harness):
    if cli_identity() != harness['codex_cli']:
        raise RuntimeError('Codex CLI differs from registration; prepare a fresh rollout')
    with isolated_home() as home:
        if digest(native_catalog(home)) != harness['native_catalog_sha256']:
            raise RuntimeError('Codex model catalog differs from registration')


def subscription_catalog(model, effort):
    """Authenticate and inspect the local app-server catalog without model inference."""
    validate_model(model)
    cli_identity()
    with isolated_home() as home, tempfile.TemporaryDirectory(prefix='workspace-') as cwd, \
            tempfile.TemporaryDirectory(prefix='codex-catalog-') as folder:
        connection = CodexRpc(command(),
            env=subscription_env(home), cwd=cwd, folder=folder)
        try:
            initialize(connection)
            account = connection.request('account/read', {'refreshToken': False}, private=True)
            identity = account.get('account') or {}
            if identity.get('type') != 'chatgpt':
                raise RuntimeError('Codex app-server does not report ChatGPT subscription auth')
            rows, cursor = [], None
            while True:
                result = connection.request('model/list', {'cursor': cursor, 'limit': 100})
                rows.extend(result['data'])
                cursor = result.get('nextCursor')
                if not cursor:
                    break
            selected = next((row for row in rows if row.get('model') == model), None)
            if selected is None:
                raise ValueError('Requested model is absent from the Codex catalog')
            supported = [row['reasoningEffort'] for row in selected['supportedReasoningEfforts']]
            if effort not in supported:
                raise ValueError('Requested reasoning effort is absent from the Codex catalog')
            return {'authentication': 'chatgpt-subscription',
                'subscription_type': identity.get('planType'), 'model': model, 'effort': effort,
                'supported_reasoning_efforts': supported, 'inference_calls': 0,
                'inference_entitlement_verified': False}
        finally:
            connection.close()


# Loaded after profile helpers so the session can import this module normally.
from codex_session import CodexAgent
from pi_agent import wait_ready, new_queue, Empty
