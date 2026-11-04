"""Minimal host-path checks shared by maintained SwarmHarm entry points."""

from copy import deepcopy
from pathlib import Path
import urllib.error
import urllib.request


def outside_repository(path, repository, label):
    resolved = Path(path).expanduser().resolve()
    repository = Path(repository).resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError(f"{label} must be outside the Git repository")
    return resolved


def credential_file(path, repository):
    if path is None:
        raise ValueError("An existing host-only AxonHub key file is required")
    resolved = outside_repository(path, repository, "AxonHub key file")
    if not resolved.is_file():
        raise ValueError("The AxonHub key file must be a regular file")
    if not resolved.read_text().strip():
        raise ValueError("The AxonHub key file is empty")
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
            raise ValueError('Claude models require Claude Code through AxonHub; Pi is not a fallback.')
        if not offline_fixture and (model.startswith('openai/') or model.startswith('gpt-')) and harness != 'codex':
            raise ValueError('OpenAI models require Codex through AxonHub; Pi is historical only.')


def native_harness(models):
    kinds=set()
    for model in models.values():
        model=str(model).lower()
        if any(name in model for name in ('claude','haiku','sonnet','opus')):
            kinds.add('claude-code')
        elif model.startswith(('openai/','gpt-')):
            kinds.add('codex')
        else:
            raise ValueError('No validated native harness for the selected model family')
    if len(kinds)!=1:
        raise ValueError('A rollout requires one native harness family')
    return kinds.pop()


def resolve_goal_mode(harness, requested=None, *, offline_fixture=False):
    """Live defaults enable the selected harness goal; off remains an explicit condition."""
    defaults = {'codex': 'codex_goal', 'claude-code': 'claude_goal', 'pi-sdk': 'goal_command'}
    if harness not in defaults:
        raise ValueError('Unknown agent harness')
    if requested is None:
        return 'off' if offline_fixture else defaults[harness]
    if requested not in ('off', defaults[harness]):
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
