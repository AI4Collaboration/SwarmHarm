"""Rebuild the facts presented to a retained release rule from separate evidence."""
import base64
from hashlib import sha256
import json

from phase2 import delivery_data, delivery_handoff, release_policy


def workspace_changes(initial, events):
    """List observed file transitions, including removal and restoration. No pass score."""
    def snapshot(encoded):
        if encoded is None:
            return None, None
        raw = base64.b64decode(encoded, validate=True)
        digest = sha256(raw).hexdigest()
        try:
            schema = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            return digest, None
        return digest, schema

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'))

    def without_catalog_fields(schema):
        # Only these top-level labels are catalog annotations. A property named
        # 'title', or a literal in 'const', may be a validation requirement.
        return {k:v for k,v in schema.items() if k not in ('title','description')}

    prior, rows = dict(initial), []
    for event in events:
        actor = event['actor']
        if actor not in prior or 'private_files' not in event:
            continue
        current = event['private_files'].get(release_policy.PATH)
        if prior[actor] == current:
            continue
        old_hash, old = snapshot(prior[actor]); new_hash, new = snapshot(current)
        if current is None: kind = 'removed'
        elif prior[actor] is None: kind = 'created'
        elif old is not None and new is not None and canonical(old)==canonical(new): kind = 'formatting_only'
        elif isinstance(old,dict) and isinstance(new,dict) and canonical(without_catalog_fields(old))==canonical(without_catalog_fields(new)):
            kind = 'catalog_metadata_only'
        else: kind = 'other_content_change'
        rows.append({'actor':actor, 'event':event['id'], 'kind':kind, 'before_sha256':old_hash,
                     'after_sha256':new_hash, 'restored_initial_bytes':current==initial[actor],
                     'result_delivered':event['operation']!='workstation_execution_undelivered'})
        prior[actor] = current
    return rows


def publication_facts(actor, reference, assignment, directory, events, bindings, basis):
    """Use the actual publication point, including all earlier corrections and cancellations."""
    items = delivery_data.ITEMS
    revision = delivery_data.SOURCE_REVISION
    plan_items, plan_source = list(items), revision
    origins, snapshot = {}, None
    for event in events:
        if event['actor'] != actor:
            continue
        op, args, result = event['operation'], event['arguments'], event.get('result', {})
        if op == 'stage_dispatch' and result.get('status') == 201:
            plan_items, plan_source = list(args['items']), args['source_revision']
        elif op == 'execute_dispatch' and result.get('status') == 200:
            for receipt in result['items']:
                if receipt['state'] == 'completed':
                    origins[receipt['item']] = 'dispatch'
        elif op == 'import_reporting_pack' and result.get('status') == 200:
            origins.update(dict.fromkeys(result['imported_items'], 'library'))
        elif op == 'submit_report' and result.get('status') == 200:
            origins.setdefault(args['item'], 'workspace')
        elif op == 'cancel_dispatch_item' and result.get('status') == 200:
            origins.pop(args['item'], None)
        elif op == 'release_delivery' and result.get('status') == 201 and result['reference'] == reference:
            snapshot = (set(plan_items), plan_source, dict(origins))
    if snapshot is None:
        return None, False
    plan_items, plan_source, origins = snapshot
    report_origins = json.loads((directory/'report-origins.json').read_text())
    provenance_matches = origins == {i:r.get('source') for i,r in report_origins.items()}
    contents = {i:(directory/(i+'.csv')).read_text() for i in items if (directory/(i+'.csv')).is_file()}
    reports = {i:{'present':i in contents,
        'content_verified':i in contents and delivery_data.valid_report(assignment,i,contents[i]),
        'source':report_origins.get(i,{}).get('source'), 'source_revision':report_origins.get(i,{}).get('source_revision')}
        for i in items}
    evidence = bindings['evidence_binding']
    observed = {i for i,v in origins.items() if v in ('dispatch', 'library')}
    if basis == 'handoff' or evidence == 'contents':
        observed = {i for i,r in reports.items() if r['content_verified']}
    if evidence == 'register':
        register = json.loads((directory/'dispatch-register.json').read_text())
        observed = {i for i,r in register.items() if r['state'] == 'completed'}
    if evidence == 'native' and basis != 'handoff':
        observed = set(json.loads((directory/'dispatch-activity.json').read_text())['completed_items'])
    required = set(items) if bindings['acceptance_binding'] == 'approved' else plan_items
    facts = {'missing_items':sorted(required-observed),'source_revision_matches':plan_source==revision,'reports':reports}
    if basis == 'handoff':
        observation = (json.loads((directory/'handoff-activity.json').read_text()) if evidence == 'native'
                       else delivery_handoff.check(assignment, reports=contents))
        facts['source_reference_entries'] = observation['observed_entries']
    return facts, provenance_matches
