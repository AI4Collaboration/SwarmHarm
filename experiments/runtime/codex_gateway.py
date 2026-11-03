"""Native Codex app-server with isolated, host-only AxonHub authentication."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import codex_agent as legacy

AXONHUB_BASE = 'https://lmportal.iefbr14.xyz/v1'
SYSTEM_PROMPT = legacy.SYSTEM_PROMPT
NATIVE_TOOLS = legacy.NATIVE_TOOLS
DISABLED_FEATURES = legacy.DISABLED_FEATURES
GOAL_MODES = ('off',)
digest = legacy.digest
catalog_profile = legacy.catalog_profile
initialize = legacy.initialize


def codex_binary():
    configured = os.environ.get('SWARMHARM_NATIVE_CODEX')
    bundled = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
    candidate = configured or (str(bundled) if bundled.is_file() else shutil.which('codex'))
    if not candidate or not Path(candidate).is_file():
        raise RuntimeError('Native Codex executable is missing')
    return str(Path(candidate).resolve())


def cli_identity():
    binary = codex_binary()
    return {'version': subprocess.check_output([binary, '--version'], text=True).strip(),
            'sha256': sha256(Path(binary).read_bytes()).hexdigest()}


def validate_model(model):
    if not model.startswith('openai/gpt-') or any(c.isspace() for c in model):
        raise ValueError('Use an explicit openai/gpt-* AxonHub model ID')


@contextmanager
def isolated_home():
    # Never read or copy the operator's subscription login/configuration.
    with tempfile.TemporaryDirectory(prefix='swarmharm-codex-') as directory:
        yield Path(directory)


def gateway_env(home, api_base=None, api_key=None):
    env = {name: os.environ[name] for name in ('PATH','USER','LOGNAME','TMPDIR','LANG','LC_ALL') if name in os.environ}
    env.update(HOME=str(home), CODEX_HOME=str(home))
    if api_base is not None or api_key is not None:
        if api_base != AXONHUB_BASE or not api_key:
            raise ValueError('Codex requires the registered AxonHub base and host key')
        env['SWARMHARM_AXONHUB_KEY'] = api_key
    return env


def native_catalog(home):
    return json.loads(subprocess.check_output([codex_binary(),'debug','models'],
        env=gateway_env(home), cwd=home, text=True, timeout=60))


def gateway_catalog(model, effort):
    validate_model(model)
    with isolated_home() as home:
        catalog = native_catalog(home)
    selected = next((row for row in catalog['models'] if row['slug'] == model.removeprefix('openai/')), None)
    if selected is None:
        raise ValueError('Requested model has no native Codex instruction profile; update Codex first')
    efforts = [row.get('effort', row.get('reasoningEffort')) for row in selected.get('supported_reasoning_levels', [])]
    if efforts and effort not in efforts:
        raise ValueError('Requested effort is unsupported by the native Codex profile')
    return {'model': model, 'native_model': selected['slug'], 'catalog_sha256': digest(catalog),
            'inference_calls': 0, 'inference_entitlement_verified': False}


def harness_registration(goal_mode, model):
    if goal_mode != 'off':
        raise ValueError('Native Codex admission currently validates goal off only')
    validate_model(model)
    with isolated_home() as home:
        catalog = native_catalog(home)
    return {'kind':'codex','authentication':'axonhub','gateway':AXONHUB_BASE,
        'codex_cli':cli_identity(), 'installed':{'codex-cli':cli_identity()['version']},
        'native_catalog_sha256':digest(catalog), 'goal_mode':'off',
        'system_prompt':SYSTEM_PROMPT, 'extension_tools':NATIVE_TOOLS, 'builtin_tools':NATIVE_TOOLS,
        'tool_profile':{'input_modalities':['text'],'apply_patch_tool_type':None,'supports_parallel_tool_calls':False},
        'disabled_features':list(DISABLED_FEATURES), 'context_window':None,
        'output_token_limit':'Codex CLI managed; no per-response override',
        'tool_execution':'controller MCP tools in isolated workstations',
        'natural_prompt_contract_covers_all_subject_input':False,
        'evidence_limit':legacy.EVIDENCE_LIMIT, 'live_validation':'pending'}


def verify_runtime(harness):
    if harness.get('authentication') != 'axonhub' or harness.get('gateway') != AXONHUB_BASE:
        raise ValueError('Unregistered Codex authentication route')
    if cli_identity() != harness['codex_cli']:
        raise RuntimeError('Codex executable changed; prepare a fresh registration')
    with isolated_home() as home:
        if digest(native_catalog(home)) != harness['native_catalog_sha256']:
            raise RuntimeError('Codex native catalog changed')


def command():
    return [codex_binary(), *[arg for feature in DISABLED_FEATURES for arg in ('--disable',feature)],
            'app-server','--listen','stdio://']


def write_config(home, workspace, definitions, endpoint, model, effort, catalog):
    validate_model(model)
    # Keep native instructions byte-for-byte; alias only the matching model slug
    # so the gateway receives its exact registered provider-prefixed identity.
    profile = catalog_profile(catalog)
    matching = [row for row in profile['models'] if row['slug'] == model.removeprefix('openai/')]
    if len(matching) != 1:
        raise ValueError('Missing or ambiguous native model profile')
    matching[0]['slug'] = model
    (home/'catalog.json').write_text(json.dumps(profile))
    import sys
    config = [f'model={json.dumps(model)}','model_provider="axonhub"',
        f'model_reasoning_effort={json.dumps(effort)}','project_doc_max_bytes=0',
        'web_search="disabled"','model_auto_compact_token_limit=2147483647',
        'model_catalog_json='+json.dumps(str(home/'catalog.json')),
        '[model_providers.axonhub]','name="AxonHub"','base_url='+json.dumps(AXONHUB_BASE),
        'env_key="SWARMHARM_AXONHUB_KEY"','wire_api="responses"','requires_openai_auth=false',
        '[mcp_servers.work]','required=true','tool_timeout_sec=300',
        'command='+json.dumps(sys.executable),
        'args='+json.dumps([str(Path(__file__).parent/'codex_mcp.py'),str(definitions),str(endpoint)]),
        '[tools.experimental_request_user_input]','enabled=false']
    (home/'config.toml').write_text('\n'.join(config)+'\n')
