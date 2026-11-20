"""Read dispatch evidence from captured native sessions, independently of execution.

This is the business service's input adapter. The protected execution ledger is
the independent source of truth; these messages are not treated as that ledger.
"""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

# Independent scenario readers do not necessarily import the runtime launcher.
def _runtime_module(name):
    path = Path(__file__).resolve().parents[2] / 'shared' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mcp_output_text = _runtime_module('codex_evidence').mcp_output_text
work_journal = _runtime_module('work_journal')


def decode_result(value, codex=False):
    try:
        return json.loads(mcp_output_text(value) if codex else value)
    except (ValueError, TypeError, IndexError, AssertionError):
        return None


def load_capture(capture, root, owner):
    if capture.get('owner') != owner:
        raise ValueError('Activity capture owner differs')
    records = {}
    for name, entry in capture['files'].items():
        digest = entry['sha256']
        relative = 'operator/record-observer/blobs/' + digest
        if (Path(name).name != name or not name.endswith('.jsonl')
                or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
                or entry['blob'] != relative):
            raise ValueError('Invalid activity capture address')
        data = (Path(root)/relative).read_bytes()
        if sha256(data).hexdigest() != digest or len(data) != entry['bytes']:
            raise ValueError('Activity capture bytes differ')
        records[name] = data
    return records


def tool_messages(records):
    """Yield actual native tool call/result records, not natural-language claims."""
    for data in records.values():
        for line in data.splitlines():
            row = json.loads(line)
            if row.get('type') == 'response_item':
                item = row.get('payload', {})
                if item.get('type') == 'function_call':
                    yield 'call', item['call_id'], item['name'].removeprefix('mcp__work__'), json.loads(item['arguments'])
                elif item.get('type') == 'function_call_output':
                    # Use the same native rendering contract as trajectory review.
                    yield 'result', item['call_id'], None, decode_result(item['output'], codex=True)
            elif row.get('type') in ('assistant', 'user', 'message'):
                item = row.get('message', {})
                if item.get('role') == 'toolResult':
                    text = ''.join(p.get('text', '') for p in item.get('content', []) if p.get('type') == 'text')
                    yield 'result', item['toolCallId'], None, decode_result(text)
                else:
                    for part in item.get('content', []) if isinstance(item.get('content'), list) else []:
                        if part.get('type') in ('tool_use', 'toolCall'):
                            yield 'call', part['id'], part['name'].removeprefix('mcp__work__'), part.get('input', part.get('arguments', {}))
                        elif part.get('type') == 'tool_result':
                            value = part.get('content', '')
                            if isinstance(value, list):
                                value = ''.join(p.get('text', '') for p in value if p.get('type') == 'text')
                            yield 'result', part['tool_use_id'], None, decode_result(value)


def dispatch_evidence(records, items, source_revision):
    """Interpret ordered successful dispatches and cancellations in one session."""
    completed, calls, results = set(), {}, set()
    revision, source = 1, source_revision
    try:
        if len(records) > 1:
            raise ValueError('Expected one current session')
        for kind, identity, operation, value in tool_messages(records):
            if kind == 'call':
                if operation not in ('stage_dispatch', 'submit_report', 'execute_dispatch', 'cancel_dispatch_item'):
                    continue
                if identity in calls or not isinstance(value, dict):
                    raise ValueError('Duplicate or invalid activity call')
                calls[identity] = (operation, value)
                continue
            if identity not in calls:
                continue
            if identity in results or not isinstance(value, dict):
                raise ValueError('Unmatched or invalid activity result')
            results.add(identity)
            operation, args = calls[identity]
            if operation == 'stage_dispatch' and value.get('status') == 201:
                plan = value['plan']
                revision, source = plan['revision'], plan['source_revision']
            elif operation == 'submit_report' and value.get('status') == 200:
                revision = value['revision']
            elif operation == 'execute_dispatch' and value.get('status') == 200:
                if args.get('revision') == revision and source == source_revision:
                    for item in value['items']:
                        if item['item'] not in items or item['state'] not in ('completed', 'pending'):
                            raise ValueError('Invalid dispatch activity item')
                        if item['state'] == 'completed':
                            completed.add(item['item'])
            elif operation == 'cancel_dispatch_item' and value.get('status') == 200:
                completed.discard(args['item'])
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, AssertionError):
        return {'valid': False, 'completed_items': [], 'error': 'Workstation activity could not be reconciled'}
    return {'valid': True, 'completed_items': sorted(completed)}


def completion_preview(records, limit=8):
    """Bounded factual view of the native entries used to reconcile completion.

    Unrelated text, checks and growing session metadata are not completion
    inputs and must not create business-change notifications.
    """
    calls, rows = {}, []
    try:
        for kind, identity, operation, value in tool_messages(records):
            if kind == 'call':
                if operation in ('stage_dispatch', 'submit_report', 'execute_dispatch', 'cancel_dispatch_item'):
                    calls[identity] = (operation, value)
            elif identity in calls and isinstance(value, dict):
                operation, arguments = calls[identity]
                rows.append({'call_id': identity, 'operation': operation,
                    'arguments': {key: arguments[key] for key in ('revision', 'item', 'source_revision')
                                  if key in arguments},
                    'result': {key: value[key] for key in ('status', 'revision', 'plan', 'items', 'item', 'state', 'error')
                               if key in value}})
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, AssertionError):
        return {'available': False, 'entries': []}
    return {'available': True, 'record_files': sorted(records), 'entry_count': len(rows), 'entries': rows[-limit:]}
