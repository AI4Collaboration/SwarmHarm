"""Read-only edition previews using an actor's saved workspace inputs."""
import base64
from copy import copy
from hashlib import sha256
from types import SimpleNamespace

from phase2 import release_policy


def preview(flow, actor, arguments):
    from workstation import resolve_workspace_path
    if arguments['revision'] != flow.plans[actor]['revision']:
        return {'status': 409, 'error': 'Plan edition has changed'}
    # The normal checker runs on a detached view. No publication, record,
    # policy or notification state is changed by a candidate input.
    view = copy(flow)
    files = dict(flow.world.private.get(actor, {}))
    view.world = SimpleNamespace(private={actor: files})
    view.activity_records = dict(flow.activity_records)
    station = getattr(flow.world, 'workstations', {}).get(actor)
    selected = {}
    for field in ('policy_path', 'activity_snapshot_path'):
        path = arguments[field]
        if path is None:
            continue
        path = resolve_workspace_path(path, getattr(station, 'native_cwd', None))
        if not path.startswith('/workspace/') or path not in files:
            return {'status': 404, 'error': 'Saved preview input not found', 'input': field}
        try:
            raw = base64.b64decode(files[path], validate=True)
        except (ValueError, TypeError):
            return {'status': 422, 'error': 'Saved preview input is unreadable', 'input': field}
        selected[field] = {'path': path, 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)}
        if field == 'policy_path':
            files[release_policy.PATH] = files[path]
        else:
            view.activity_records[actor] = {'workspace-activity-snapshot.jsonl': raw}
    return {'status': 200, 'revision': flow.plans[actor]['revision'],
            'saved_inputs': selected, 'check': view._check(actor)}
