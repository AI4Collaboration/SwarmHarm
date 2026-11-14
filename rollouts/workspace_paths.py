"""Pure path normalization shared by workstations and offline replay."""
import posixpath


def resolve_workspace_path(path, native_cwd=None):
    """Resolve a business file using only this actor's workstation alias."""
    if not isinstance(path, str):
        return path
    if native_cwd and (path == native_cwd or path.startswith(native_cwd + '/')):
        path = '/workspace' + path[len(native_cwd):]
    if not path.startswith('/'):
        path = '/workspace/' + path
    return posixpath.normpath(path)
