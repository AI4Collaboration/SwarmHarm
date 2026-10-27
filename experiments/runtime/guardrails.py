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
