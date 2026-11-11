"""Expose one actor's work entries without exposing the recorder's own files."""
from difflib import SequenceMatcher
import json


FILENAME = 'current.jsonl'


def work_entry(line):
    row = json.loads(line)
    if not isinstance(row, dict):
        return False
    if row.get('type') == 'response_item':
        item = row.get('payload', {})
        if item.get('type') == 'message':
            return item.get('role') in ('user', 'assistant')
        return item.get('type') in ('function_call', 'function_call_output')
    if row.get('type') in ('message', 'user', 'assistant'):
        return row.get('message', {}).get('role') in ('user', 'assistant', 'toolResult')
    return False


def view(records):
    if not records:
        return {}
    if len(records) != 1:
        raise ValueError('Expected one current activity file per workstation')
    data, = records.values()
    return {FILENAME: b''.join(line for line in data.splitlines(keepends=True) if work_entry(line))}


def native_edit(records, visible, edited):
    """Put a work edit back into its native slots, retaining recorder-only lines."""
    if not records or edited.get(FILENAME) == visible.get(FILENAME):
        return records
    name, data = next(iter(records.items()))
    native_lines = data.splitlines(keepends=True)
    positions = [i for i, line in enumerate(native_lines) if work_entry(line)]
    old = [native_lines[i] for i in positions]
    new = edited.get(FILENAME, b'').splitlines(keepends=True)
    if any(not work_entry(line) for line in new):
        raise ValueError('Unrecognized activity entry')
    # A text editor may omit the final newline. Native writers append by line.
    if new and not new[-1].endswith(b'\n'):
        new[-1] += b'\n'

    # Walk backwards so edits never invalidate positions in the original file.
    for operation, start, stop, begin, end in reversed(
            SequenceMatcher(None, old, new, autojunk=False).get_opcodes()):
        if operation == 'equal':
            continue
        slots = positions[start:stop]
        replacement = new[begin:end]
        for offset, slot in enumerate(slots):
            native_lines[slot] = replacement[offset] if offset < len(replacement) else b''
        if len(replacement) > len(slots):
            anchor = slots[-1]+1 if slots else (positions[start] if start < len(positions) else len(native_lines))
            native_lines[anchor:anchor] = replacement[len(slots):]
    return {name: b''.join(native_lines)}
