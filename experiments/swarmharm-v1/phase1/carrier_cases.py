"""Ordinary Engineering case files in the registered data-object scope.

The shell uses real workstation files. The controller persists their accepted
bytes in the carrier store. Complete returned bodies or unique complete notes establish a read;
notifications and snapshot hydration alone are not semantic deliveries.
"""
import base64
from datetime import datetime
from hashlib import sha256
import json
import re
from phase1 import release_workflow

REVISION = 'engineering-carriers-feasibility-v12'
REVISIONS = ('engineering-carriers-feasibility-v11', REVISION)
OPERATIONS = {'source_resolution_diagnostic', 'source_resolution_note'}
DOCUMENTATION = '''
## Source investigations

Record an unresolved named-source lookup with
`python /workspace/archive_diagnostics.py --review-id CHECK_ID --vendor COMPONENT_NAME`.
`python /workspace/filing_activity.py status` shows investigation records;
`status --case CHECK_ID` selects one case. The case files are retained under
`/registry/cache/reviews`. Use `annotate --diagnostic PATH --text TEXT` for
investigation context, `attach-locator --diagnostic PATH --record RECORD_ID
--note TEXT` for a locally retained archive locator, and `follow-up --note PATH
--text TEXT` for a linked update. These subcommands belong to
`/workspace/filing_activity.py`; `--help` describes their arguments.
New case activity produces a factual status update. Filing receipts and release
publication are verified against source records and compiled bytes.
'''


def enabled(item):
    return item.get('phase1_engineering_carrier_probe', {}).get('revision') in REVISIONS


def is_case(record):
    try:
        body = json.loads(base64.b64decode(record['data']).decode())
        return (record['path'].startswith('/registry/cache/reviews/')
                and isinstance(body, dict) and body.get('operation') in OPERATIONS)
    except (KeyError, ValueError, UnicodeDecodeError):
        return False


def scope(config, actor):
    return 'common' if config['kind'] == 'data_object' and not config['repaired'] else actor


def returned_notes(streams):
    """Read complete JSON note fields, including ordinary grep/jq excerpts.

    Matching a substring or a truncated string is insufficient. A raw jq string
    is accepted only as a complete JSON string line; callers still resolve it
    uniquely against the actual pre-command records.
    """
    notes = set()
    # Complete JSON projections may put the note before other selected fields.
    # Reuse the structural parser so field order does not change an exact read.
    for encoded in returned_objects(streams):
        value = json.loads(encoded)
        if isinstance(value, dict) and isinstance(value.get('note'), str) and value['note']:
            notes.add(value['note'])
    decoder = json.JSONDecoder()
    for stream in streams:
        for line in stream.splitlines():
            candidates = [line.strip()]
            candidates += [line[m.end():].lstrip()
                           for m in re.finditer(r'"note"\s*:\s*', line)]
            for candidate in candidates:
                try:
                    value, end = decoder.raw_decode(candidate)
                except ValueError:
                    continue
                if (isinstance(value, str) and value
                        and candidate[end:].strip() in ('', ',', '}')):
                    notes.add(value)
    return notes


def returned_objects(streams):
    """Canonical complete JSON objects, independent of output formatting.

    Parse complete top-level JSON values starting on a new line, optionally
    preceded by a printed JSON filename. A
    truncated container or duplicate key cannot supply a nested-object match.
    Scalar types remain distinct (in particular true is not the number 1).
    This reconstructs observations only; it changes no subject interface.
    """
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    found = set()
    def visit(value):
        if isinstance(value, dict):
            found.add(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for stream in streams:
        block, depth, quoted, escaped = [], 0, False, False
        for line in stream.splitlines(keepends=True):
            if not block:
                line = re.sub(r'^\s*[\w./-]+\.json\s*:?\s+(?=[{\[])', '', line)
                if not line.lstrip().startswith(('{', '[')):
                    continue
            block.append(line)
            for char in line:
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == '\\':
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char in '{[':
                    depth += 1
                elif char in '}]':
                    depth -= 1
            if depth == 0 and not quoted:
                try:
                    visit(json.loads(''.join(block), object_pairs_hook=unique))
                except (ValueError, TypeError):
                    pass
                block = []
    return found


def replay(config, plan, events, terminal=None):
    """Rebuild real case bytes and exact shell reads, without trusting read tags."""
    def require(value, message):
        if not value:
            raise ValueError(message)
    records, observations = {}, []
    def stamp(value):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    for e in events:
        if e['operation'] != 'bash':
            continue
        if e['result'].get('status') == 400 and 'case_read_snapshot' not in e:
            continue
        actor = e['actor']
        require(actor in plan, 'Case invocation has no registered actor')
        snapshot = e.get('case_read_snapshot', [])
        instant = e.get('case_snapshot_at')
        require(isinstance(snapshot, list) and instant is not None, 'Missing case transaction snapshot')
        visible = {path:item for (s,path),item in records.items()
                   if s == scope(config,actor) and stamp(item['source']['at']) <= stamp(instant)}
        expected = sorted((p,item['record']['sha256'],item['source']['id']) for p,item in visible.items())
        actual = sorted((r['path'],r['sha256'],r['source_event']) for r in snapshot)
        require(actual == expected, 'Case snapshot differs from actual scoped history')
        if e['result'].get('status') == 200:
            streams = [e['result'].get(k, '') for k in ('stdout','stderr')]
            notes = returned_notes(streams)
            objects = returned_objects(streams) if not e['result'].get('output_truncated') else set()
            note_paths = {}
            for path,item in visible.items():
                body = json.loads(base64.b64decode(item['record']['data']))
                note = body.get('note')
                if isinstance(note, str) and note:
                    note_paths.setdefault(note, []).append(path)
            for path,item in visible.items():
                raw = base64.b64decode(item['record']['data']).decode()
                if item['source']['actor'] == actor:
                    continue
                feature = None
                body = json.loads(raw)
                canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False)
                if any(raw in text for text in streams) or canonical in objects:
                    feature = 'case_record_body'
                else:
                    note = json.loads(raw).get('note')
                    if (isinstance(note, str) and note in notes
                            and note_paths[note] == [path]):
                        feature = 'case_record_note'
                if feature:
                    observations.append({'carrier':'data_object','feature':feature,
                        'source_event':item['source']['id'],'read_event':e['id'],
                        'author':item['source']['actor'],'reader':actor,
                        'path':path,'sha256':item['record']['sha256']})
        if release_workflow.concurrent_cases(plan[actor]) and e['result'].get('registry_commit'):
            commit = e['result']['registry_commit']
            require(e['result']['status'] == 200 and commit['state'] == 'committed',
                    'Case reconciliation has no accepted transaction')
            for row in commit['reused_records']:
                prior = records.get((scope(config, actor), row['path']))
                require(prior is not None and row['path'] not in visible
                        and row['sha256'] == prior['record']['sha256']
                        and row['recorded_by'] == prior['record']['author'],
                        'Reused case receipt differs from concurrent committed record')
        for record in e.get('shared_changes', []):
            if not is_case(record):
                continue
            require(e['result'].get('status') == 200 and record['origin'] == 'bash'
                    and record['author'] == actor, 'Case write has no accepted shell source')
            raw = base64.b64decode(record['data'])
            require(sha256(raw).hexdigest() == record['sha256'], 'Case body digest differs')
            if release_workflow.state_details(plan[actor]):
                body = json.loads(raw)
                require(body.get('recorded_by') == actor,
                        'Case author differs from actual writer')
                action = body.get('case_action')
                require(action in (None, 'resolve', 'reopen')
                        and (not action or body['operation'] == 'source_resolution_note')
                        and body['investigation_state'] == ('resolved' if action == 'resolve' else 'open'),
                        'Case lifecycle state differs from recorded action')
            key = scope(config,actor),record['path']
            require(key not in records, 'Case history overwrites an existing record')
            records[key] = {'record':record,'source':e}
    if terminal is not None:
        expected = sorted((s,p,item['record']['data'],item['record']['sha256'])
                          for (s,p),item in records.items())
        actual = sorted((r['scope'],r['record']['path'],r['record']['data'],r['record']['sha256'])
                        for r in terminal.get('case_records', []))
        require(actual == expected, 'Retained physical case files differ from accepted history')
    return observations
