"""Minimal host-path checks shared by maintained SwarmHarm entry points."""

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
