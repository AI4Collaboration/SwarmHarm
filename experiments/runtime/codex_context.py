"""Registered opaque context maintenance; never a research or social response."""
from copy import deepcopy
import json


POLICY = {
    'version': 'opaque-context-v1',
    'implementation': 'native Codex remote compaction v2',
    'auto_compact_token_limit': 200000,
    'provider_capability': 'v2',
    'background_compaction': False,
    'model': 'same registered model',
    'new_controller_text': None,
    'local_text_summary_allowed': False,
    'budget': 'research plus observed maintenance input/output tokens and responses',
    'clock': 'maintenance consumes the existing research wall clock',
    'projection': 'archival research history; native checkpoints define compacted context',
}


def policy(value):
    if value is not None and value != POLICY:
        raise ValueError('Unknown context maintenance policy; fresh registration required')
    return deepcopy(value)


class ContextLifecycle:
    """Strict pinned-protocol recognizer, also used by evidence and timing readers."""
    def __init__(self):
        self.active = None
        self.epoch = 0
        self.responses = set()
        self.completed = []
        self.interrupted = []
        self.closed = False

    def observe(self, message, source):
        method = message.get('method')
        params = message.get('params') or {}
        item = params.get('item') or {}
        if self.closed and method in ('turn/started', 'rawResponseItem/completed'):
            raise ValueError('Research resumed after interrupted context maintenance')
        if method == 'thread/compacted':
            raise ValueError('Unexpected legacy compaction protocol')
        if item.get('type') == 'contextCompaction':
            if method == 'item/started':
                if self.active or not item.get('id'):
                    raise ValueError('Overlapping or unidentified context maintenance')
                self.active = {'id': item['id'], 'start': source, 'usage_records': []}
                return {'type': 'context_maintenance', 'phase': 'started', 'epoch': self.epoch + 1,
                        'native_record': source}
            if method != 'item/completed' or not self.active or self.active['id'] != item.get('id'):
                raise ValueError('Unmatched context maintenance completion')
            if not self.active['usage_records']:
                raise ValueError('Missing context maintenance usage')
            self.epoch += 1
            self.completed.append({**self.active, 'end': source, 'epoch': self.epoch})
            self.active = None
            return {'type': 'context_maintenance', 'phase': 'completed', 'epoch': self.epoch,
                    'native_record': source}
        if not self.active:
            return None
        if method == 'turn/completed' and params.get('turn', {}).get('status') == 'interrupted':
            self.interrupted.append({**self.active, 'end': source})
            self.active = None
            self.closed = True
            return {'type': 'context_maintenance', 'phase': 'interrupted',
                    'epoch': self.epoch, 'native_record': source, 'checkpoint_completion_verified': False}
        if method == 'rawResponse/completed':
            identity = params.get('responseId')
            usage = params.get('usage') or {}
            if not identity or identity in self.responses:
                raise ValueError('Missing or duplicate context response identity')
            if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('inputTokens', 'outputTokens')):
                raise ValueError('Missing context maintenance token accounting')
            self.responses.add(identity)
            self.active['usage_records'].append(source)
            return {'type': 'context_usage', 'id': identity, 'native_record': source,
                    'usage': {'input_tokens': usage['inputTokens'], 'output_tokens': usage['outputTokens']}}
        if method == 'thread/tokenUsage/updated':
            # This is a new context SIZE, not another paid response. Native
            # cumulative research totals also exclude maintenance responses.
            return {'type': 'context_size', 'native_record': source,
                    'token_usage': params.get('tokenUsage')}
        if method in ('rawResponseItem/completed', 'turn/completed', 'turn/started'):
            raise ValueError('Research event inside context maintenance')
        return None


def validate_checkpoints(session_file, expected):
    """Require opaque replacements and no newly authored plaintext handoff."""
    known = set()
    checkpoints = []
    for line in session_file.read_text().splitlines():
        row = json.loads(line)
        payload = row.get('payload') or {}
        if row.get('type') == 'response_item' and payload.get('type') == 'message':
            known.add(json.dumps(payload.get('content'), sort_keys=True))
        if row.get('type') != 'compacted':
            continue
        if payload.get('message') != '':
            raise ValueError('Textual context handoff is outside the registered policy')
        items = payload.get('replacement_history') or []
        opaque = [x for x in items if x.get('type') == 'compaction']
        if len(opaque) != 1 or not opaque[0].get('encrypted_content'):
            raise ValueError('Missing opaque context checkpoint')
        for item in items:
            if item.get('type') == 'compaction':
                continue
            if item.get('type') != 'message' or json.dumps(item.get('content'), sort_keys=True) not in known:
                raise ValueError('Context maintenance introduced unrecognized plaintext')
        checkpoints.append({'ordinal': row.get('ordinal'), 'timestamp': row['timestamp'],
                            'compaction_id': opaque[0].get('id')})
    if len(checkpoints) != expected:
        raise ValueError('Native checkpoints and lifecycle completions differ')
    return checkpoints
