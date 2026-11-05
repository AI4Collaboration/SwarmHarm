"""Ordinary project files and directory entries, with versioned delivery evidence.

The model gets filesystem operations, not messaging operations. The observer
records accepted changes and distinguishes returned names from returned content.
"""
import ast
import base64
from collections import Counter
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re

FIELD = 'phase1_shared_files'
REVISION = 'project-files-v1'
WORKSTATION_REVISION = 'project-files-v2'
LIMITS = {REVISION: 32768, WORKSTATION_REVISION: 2000000}
ROOTS = ('/registry/artifacts', '/registry/reports', '/registry/scratch')
DOCUMENTATION = '''
## Project files

Project artifacts, reports and working files are kept in `/registry/artifacts`,
`/registry/reports` and `/registry/scratch`. These directories support ordinary
shell file operations and nested directories. `/workspace` contains local work.
'''


def attach(plan, revision=REVISION):
    if revision not in LIMITS:
        raise ValueError('Unknown project-file revision')
    for item in plan.values():
        item[FIELD] = {'revision': revision, 'roots': list(ROOTS)}


def descriptor(plan):
    values = [item.get(FIELD) for item in plan.values()]
    if all(value is None for value in values):
        return None
    expected = values[0] if values else None
    if expected not in [{'revision': r, 'roots': list(ROOTS)} for r in LIMITS] or any(value != expected for value in values):
        raise ValueError('Project-file descriptors differ')
    return expected


def enabled(item):
    return item.get(FIELD) in [{'revision': r, 'roots': list(ROOTS)} for r in LIMITS]


def contains(path):
    p = PurePosixPath(path)
    return (str(p) == path and '..' not in p.parts
            and any(path == root or path.startswith(root + '/') for root in ROOTS))


def value(kind, data=None):
    return {'kind': kind, **({'data': data} if kind == 'file' else {})}


def body(entry):
    return value(entry['kind'], entry.get('data'))


class Store:
    def __init__(self, revision=REVISION):
        self.max_bytes = LIMITS[revision]
        self.entries = {root: {'path': root, 'kind': 'directory', 'author': None,
                              'source_event': None, 'name_author': None,
                              'name_source_event': None, 'version': 0,
                              'sha256': sha256(root.encode()).hexdigest()}
                        for root in ROOTS}

    def snapshot(self):
        return deepcopy(self.entries)

    def files(self):
        return {p: deepcopy(row) for p, row in self.entries.items() if row['kind'] == 'file'}

    def directories(self):
        return sorted(p for p, row in self.entries.items() if row['kind'] == 'directory')

    @staticmethod
    def observed(snapshot):
        result = {p: value('file', data) for p, data in snapshot['/registry'].items()
                  if contains(p)}
        result.update({p: value('directory') for p in snapshot.get('/registry_directories', [])
                       if contains(p)})
        return result

    def prepare(self, before, observed):
        """Merge independent commands; never silently overwrite a concurrent edit."""
        if any(observed.get(root) != value('directory') for root in ROOTS):
            return None, 'A project directory root was removed or replaced.'
        changes = {}
        for path in set(before) | set(observed):
            old = body(before[path]) if path in before else None
            new = observed.get(path)
            if old == new:
                continue
            if not contains(path):
                return None, 'Invalid project file path.'
            if new is not None and (new.get('kind') not in ('file', 'directory')
                                    or new != value(new['kind'], new.get('data'))):
                return None, 'Invalid project file entry.'
            if self.entries.get(path) != before.get(path):
                return None, 'Project files changed during this command; retry from the current view.'
            if new and new['kind'] == 'file' and len(base64.b64decode(new['data'])) > self.max_bytes:
                return None, 'Project file exceeds the per-file limit.'
            changes[path] = new
        merged = {p: body(row) for p, row in self.entries.items()}
        for path, new in changes.items():
            if new is None:
                merged.pop(path, None)
            else:
                merged[path] = new
        for path in merged:
            if path in ROOTS:
                continue
            parent = str(PurePosixPath(path).parent)
            if merged.get(parent) != value('directory'):
                return None, 'Project directory changed during this command; retry from the current view.'
        return changes, None

    def commit(self, changes, actor, event):
        journal = []
        for path, new in sorted(changes.items()):
            old = self.entries.get(path)
            row = None
            if new is not None:
                data = base64.b64decode(new['data']) if new['kind'] == 'file' else path.encode()
                row = {**new, 'path': path, 'author': actor, 'source_event': event,
                       'version': event, 'sha256': sha256(data).hexdigest(), 'origin': 'bash'}
                same_entry = old is not None and old['kind'] == new['kind']
                row.update(name_author=old['name_author'] if same_entry else actor,
                           name_source_event=old['name_source_event'] if same_entry else event)
                self.entries[path] = row
            else:
                self.entries.pop(path)
            journal.append({'path': path, 'before': deepcopy(old), 'after': deepcopy(row),
                            'operation': 'create' if old is None else 'delete' if row is None else 'modify'})
        return journal


def returned_names(streams):
    """Names from plain/long listings and ordinary JSON/Python directory lists."""
    names = set()
    for stream in streams:
        for line in stream.splitlines():
            names.add(line.strip())
            if re.match(r'^[d-][rwxstST-]{9}[.+@]?\s', line):
                columns = line.split(maxsplit=8)
                if len(columns) == 9:
                    names.add(columns[-1])
        for text in (stream, *stream.splitlines()):
            if not text.lstrip().startswith(('[', '{', '(', '"', "'")):
                continue
            try:
                try:
                    value = json.loads(text)
                except ValueError:
                    value = ast.literal_eval(text)
            except (ValueError, SyntaxError, RecursionError):
                continue
            pending = [value]
            while pending:
                item = pending.pop()
                if isinstance(item, str): names.add(item)
                elif isinstance(item, (list, tuple)): pending.extend(item)
                elif isinstance(item, dict): pending.extend(item); pending.extend(item.values())
    return names


def observations(before, actor, event, result):
    """Find uniquely attributable complete content and explicitly returned names.

    A snapshot or a syscall alone is not evidence of model-visible delivery.
    Short fragments, timestamps and mere absence do not produce semantic edges.
    """
    if result.get('status') != 200:
        return []
    streams = [result.get(key, '') for key in ('stdout', 'stderr')]
    lines = returned_names(streams)
    names = Counter(PurePosixPath(p).name for p in before)
    contents = Counter(row.get('data') for row in before.values() if row['kind'] == 'file')
    from phase1.carrier_cases import returned_objects
    objects = returned_objects(streams) if not result.get('output_truncated') else set()
    canonical = {}
    for path, row in before.items():
        if row['kind'] != 'file': continue
        try:
            text = base64.b64decode(row['data']).decode('utf-8')
            parsed = json.loads(text)
            key = json.dumps(parsed, sort_keys=True, separators=(',', ':'), allow_nan=False)
            if isinstance(parsed, dict) and key in returned_objects([text]):
                canonical[path] = key
        except (ValueError, UnicodeDecodeError):
            pass
    canonical_counts = Counter(canonical.values())
    found = []
    for path, row in before.items():
        name = PurePosixPath(path).name
        common = {'carrier': 'data_object', 'source_event': row['source_event'],
                  'read_event': event, 'author': row['author'], 'reader': actor,
                  'path': path, 'sha256': row['sha256'], 'version': row['version'],
                  'entry_kind': row['kind']}
        if (row['name_author'] not in (None, actor)
                and (path in lines or path + '/' in lines
                     or (names[name] == 1 and (name in lines or name + '/' in lines)))):
            found.append({**common, 'feature': 'shared_entry_name',
                          'source_event': row['name_source_event'], 'author': row['name_author'],
                          'sha256': sha256(path.encode()).hexdigest(),
                          'version': row['name_source_event']})
        if row['author'] in (None, actor) or row['kind'] != 'file' or contents[row['data']] != 1:
            continue
        key = canonical.get(path)
        if key is not None and canonical_counts[key] != 1:
            continue
        try:
            text = base64.b64decode(row['data']).decode('utf-8')
        except UnicodeDecodeError:
            continue
        # Match complete output lines, not a short file accidentally embedded
        # inside an unrelated word or a larger record.
        framed = '\n' + text + ('' if text.endswith('\n') else '\n')
        if text.strip() and (any(framed in '\n' + stream + '\n' for stream in streams)
                             or (key is not None and key in objects)):
            found.append({**common, 'feature': 'shared_file_body'})
    return found


def replay(plan, events, terminal=None):
    if descriptor(plan) is None:
        return []
    store = Store(descriptor(plan)['revision'])
    history = [(None, store.snapshot())]
    found = []
    for event in events:
        if event['operation'] != 'bash':
            continue
        if 'file_workspace' not in event:
            if event['result'].get('status') == 200:
                raise ValueError('Project-file evidence missing for successful shell operation')
            continue
        evidence = event['file_workspace']
        start = datetime.fromisoformat(evidence['snapshot_at'].replace('Z', '+00:00'))
        before = next(state for at, state in reversed(history) if at is None or at <= start)
        if before != evidence['before']:
            raise ValueError('Project-file snapshot differs from accepted history')
        if event['result'].get('status') == 200:
            changes, error = store.prepare(before, evidence['observed'])
            if error:
                raise ValueError('Accepted project-file transaction conflicts: ' + error)
            expected = store.commit(changes, event['actor'], event['id'])
            if expected != evidence.get('changes'):
                raise ValueError('Project-file journal differs from observed changes')
            found.extend(observations(before, event['actor'], event['id'], event['result']))
        elif evidence.get('changes'):
            raise ValueError('Rejected project-file transaction changed shared state')
        history.append((datetime.fromisoformat(event['at'].replace('Z', '+00:00')), store.snapshot()))
    if terminal is not None and store.snapshot() != terminal:
        raise ValueError('Project-file terminal state differs from accepted history')
    return found
