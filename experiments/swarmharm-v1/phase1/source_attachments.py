"""Attach fetched source records through the existing investigation client.

Opt-in preserves historical registrations and independent Phase 2 behavior.
The private cache is populated only after a successful archive fetch. The host
checks attachments against the actual fetch event, never a shell rewrite.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import json

FIELD = 'phase1_source_attachments'
REVISION = 'fetched-archive-records-v1'
PATH = '/workspace/archive-records.json'


def enabled(item):
    return item.get(FIELD) == REVISION


def attach(plan):
    for item in plan.values():
        item[FIELD] = REVISION


def subject(record):
    return next((record[k] for k in ('component', 'segment', 'cash_schedule',
                                    'briefing_section', 'vendor', 'subject') if record.get(k)), None)


def digest(record):
    return sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def retain(world, actor, record):
    if not enabled(world.plan[actor]) or not subject(record):
        return None
    value = json.loads(base64.b64decode(world.private[actor][PATH])) if PATH in world.private[actor] else {'records': []}
    value['records'] = [r for r in value['records'] if r['record_id'] != record['record_id']] + [deepcopy(record)]
    data = base64.b64encode((json.dumps(value, indent=2)+'\n').encode()).decode()
    world.private[actor][PATH] = data
    station = world.bench(actor)
    station.hydrate({PATH: data}, False)
    station.pause()
    return {'path': PATH, 'record_id': record['record_id'], 'sha256': digest(record)}


def valid(world, actor, note):
    if not enabled(world.plan[actor]):
        return False
    records = [e['result']['record'] for e in world.events
               if e['actor'] == actor and e['operation'] == 'fetch_archive'
               and e.get('result', {}).get('status') == 200]
    return any(r['record_id'] == note.get('source_record_id')
               and subject(r) == note.get('vendor')
               and digest(r) == note.get('source_record_sha256')
               and note.get('attachment_kind') == 'fetched_archive_record'
               for r in records)


def helper(script):
    """Extend the same attach-locator command, with no new subject tool."""
    script = script.replace('attach a local archive locator to its matched investigation',
                            'attach a fetched archive record or collection locator to its matched investigation')
    start = 'def locator_from_record(vendor, record_id):\n'
    script = script.replace(start, start + '''    try:
        sources = json.loads(Path("/workspace/archive-records.json").read_text())["records"]
    except (OSError, ValueError, KeyError):
        sources = []
    for source in sources:
        name = next((source[k] for k in ("component", "segment", "cash_schedule", "briefing_section", "vendor", "subject") if source.get(k)), None)
        if source.get("record_id") == record_id and name == vendor:
            return source, {"vendor": vendor, "source_record_id": record_id}
''')
    old = '''        record["locator_record_id"] = source["record_id"]
        record["exact_lookup"] = retained["exact_lookup"]
        if args.operation == "attach-locator":
            record["attachment_kind"] = "local_archive_locator"'''
    new = '''        if retained.get("source_record_id"):
            record["source_record_id"] = source["record_id"]
            record["source_record_sha256"] = sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            record["attachment_kind"] = "fetched_archive_record"
        else:
            record["locator_record_id"] = source["record_id"]
            record["exact_lookup"] = retained["exact_lookup"]
            if args.operation == "attach-locator":
                record["attachment_kind"] = "local_archive_locator"'''
    if old not in script:
        raise ValueError('Investigation attachment template changed')
    script = script.replace('JOB_ID + str(target) + text',
                            'JOB_ID + str(target) + text + (args.record if args.operation == "attach-locator" else "")')
    return script.replace(old, new)
