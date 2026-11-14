"""Minimal host-path checks shared by maintained SwarmHarm entry points."""

from copy import deepcopy
import os
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def outside_repository(path, repository, label):
    resolved = Path(path).expanduser().resolve()
    repository = Path(repository).resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError(f"{label} must be outside the Git repository")
    return resolved


def require_unified_workflow(mode, family):
    if (mode, family) != ('unified', 'unified-delivery'):
        raise ValueError('Live rollouts require study mode unified and family unified-delivery.')


def require_unified_backend():
    if os.environ.get('SWARMHARM_SANDBOX', 'docker') != 'docker':
        raise ValueError('Unified live workstations require Docker for the isolated reporting-library links.')


def api_base_url(value):
    value = str(value).rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or any(c.isspace() for c in value)):
        raise ValueError('API base must be an HTTP(S) URL without credentials, query or fragment')
    if parsed.path.endswith(('/responses', '/chat/completions', '/messages')):
        raise ValueError('Use the API base URL, including its version path, without an endpoint suffix')
    return value


def credential_file(path, repository):
    if path is None:
        raise ValueError("An existing host-only API key file is required")
    resolved = outside_repository(path, repository, "API key file")
    if not resolved.is_file():
        raise ValueError("The API key file must be a regular file")
    if not resolved.read_text().strip():
        raise ValueError("The API key file is empty")
    return resolved


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise urllib.error.HTTPError(
            request.full_url, code, "Provider redirects are disabled", headers, fp
        )


def open_url(request, timeout):
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout)


def validate_model_harness(models, harness, *, offline_fixture=False, pi_comparison=False):
    """Current live selection policy; offline fixture preparation cannot collect."""
    if pi_comparison:
        if harness != 'pi-sdk' or not models or set(models.values()) != {'openai/gpt-5.6-sol'}:
            raise ValueError('The explicit Pi comparison requires openai/gpt-5.6-sol and pi-sdk')
        return
    for model in models.values():
        model = str(model).lower()
        if any(name in model for name in ('claude', 'haiku', 'sonnet', 'opus')) and harness != 'claude-code':
            raise ValueError('Claude models require Claude Code; Pi is not a fallback.')
        if not offline_fixture and (model.startswith('openai/') or model.startswith('gpt-')) and harness != 'codex':
            raise ValueError('OpenAI models require Codex outside the explicit Sol 5.6 Pi comparison.')
        if not offline_fixture and harness == 'pi-sdk' and not model.startswith(('google/', 'moonshotai/', 'z-ai/', 'deepseek/')):
            raise ValueError('Pi is for the selected non-OpenAI/non-Claude families; use the explicit Sol 5.6 Pi comparison for that model')


def native_harness(models):
    kinds=set()
    for model in models.values():
        model=str(model).lower()
        if any(name in model for name in ('claude','haiku','sonnet','opus')):
            kinds.add('claude-code')
        elif model.startswith(('openai/','gpt-')):
            kinds.add('codex')
        elif model.startswith(('google/', 'moonshotai/', 'z-ai/', 'deepseek/')):
            kinds.add('pi-sdk')
        else:
            raise ValueError('Unknown model family; select a lineup identity and map its served ID')
    if len(kinds)!=1:
        raise ValueError('A rollout requires one native harness family')
    return kinds.pop()


def resolve_goal_mode(harness, requested=None, *, offline_fixture=False):
    """New rollouts default to off. Explicit goals use the selected native harness."""
    native_modes = {'codex': 'codex_goal', 'claude-code': 'claude_goal', 'pi-sdk': 'goal_command'}
    if harness not in native_modes:
        raise ValueError('Unknown agent harness')
    if requested is None:
        return 'off'
    if requested not in ('off', native_modes[harness]):
        raise ValueError('Goal mode does not match the selected harness')
    return requested


def require_same_harness(registered, current):
    """Reject silent settings drift, including newly added contract fields."""
    if 'input_projection' in registered:
        current = controller_harness(current)
    for field in sorted(set(registered) | set(current)):
        if field not in registered or field not in current or registered[field] != current[field]:
            raise RuntimeError(f'Harness settings changed: {field}; prepare a fresh registration')


def controller_harness(harness):
    """One definition for the collector-owned execution and input contract."""
    value=deepcopy(harness)
    kind=value['kind']
    value['input_projection']={
        'business_task':'user',
        'declared_context':'system_append' if kind=='pi-sdk' else 'user',
        'autonomous_execution_rule':'system_append' if kind=='claude-code' else 'initial_context',
        'authoritative_evidence':'native_harness_records',
    }
    value['tool_execution']='controller; concurrent private shell, serialized shared-state commits'
    return value
