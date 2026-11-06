"""Read-only edition previews using an actor's workspace or captured native inputs."""
import base64
from copy import copy, deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from phase2 import release_policy


_spec = importlib.util.spec_from_file_location(
    'unified_workspace_paths', Path(__file__).resolve().parents[2] / 'runtime/workspace_paths.py')
_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paths)


def preview(flow, actor, arguments):
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
        path = _paths.resolve_workspace_path(path, getattr(station, 'native_cwd', None))
        activity_dir = ('/tmp/agent/.pi/sessions'
                        if flow.plan[actor].get('native_record_harness') == 'pi-sdk'
                        else '/tmp/agent/activity')
        name = Path(path).name
        if (field == 'activity_snapshot_path' and path == activity_dir + '/' + name
                and name in flow.activity_records[actor]):
            raw = flow.activity_records[actor][name]
        elif path.startswith('/workspace/') and path in files:
            try:
                raw = base64.b64decode(files[path], validate=True)
            except (ValueError, TypeError):
                return {'status': 422, 'error': 'Saved preview input is unreadable', 'input': field}
        else:
            return {'status': 404, 'error': 'Preview input file not found', 'input': field}
        selected[field] = {'path': path, 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)}
        if field == 'policy_path':
            destination = release_policy.selected_path(files, flow.config['descriptor_delivery'])
            if destination is None:
                return {'status': 422, 'error': 'The edition manifest does not name an available descriptor'}
            files[destination] = files[path]
        else:
            view.activity_records[actor] = {'workspace-activity-snapshot.jsonl': raw}
    required, observed, _ = view._observed_items(actor)
    facts = view._release_facts(actor, required, observed)
    check = view._check(actor)
    # Inspection is a separate action from receiving release-check feedback.
    # Show the edition and the actual selected inputs, not another status widget.
    check.pop('input_preview', None)
    return {'status': 200, 'revision': flow.plans[actor]['revision'],
            'saved_inputs': selected,
            'reports': deepcopy(view.outputs[actor]),
            'inputs': view._input_preview(actor, facts), 'check': check}
