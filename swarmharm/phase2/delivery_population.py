"""Reporting-population selection, with separately retained approved coverage.

The service executes canonical domain reductions, never model-authored code.
Only a declarative list of source references can vary the reporting population.
"""
import base64
import json

from phase2 import delivery_data, release_policy


PATH = 'reporting-population.json'


def enabled(config):
    return config['access'].get('population_plan') == 'workspace'


def approved(assignment):
    return [row[0] for row in delivery_data.reference_data(assignment)['rows']]


def document(assignment, references=None):
    return json.dumps({'account': assignment['account'],
        'source_revision': delivery_data.SOURCE_REVISION,
        'references': approved(assignment) if references is None else list(references)}, indent=2)+'\n'


def parse(assignment, text):
    try:
        value = json.loads(text)
        refs = value['references']
        if (set(value) != {'account', 'source_revision', 'references'}
                or value['account'] != assignment['account']
                or value['source_revision'] != delivery_data.SOURCE_REVISION
                or not isinstance(refs, list) or not refs
                or any(not isinstance(r, str) for r in refs)
                or len(set(refs)) != len(refs) or not set(refs) <= set(approved(assignment))):
            return None
        return sorted(refs)
    except (TypeError, ValueError, KeyError):
        return None


def assignment(base, references):
    return dict(base, population_references=list(references))


def process(flow, actor):
    """Materialize one source population atomically, with no charge on rejection."""
    base = flow.plan[actor]
    selected = parse(base, release_policy.workspace_text(flow.world.private[actor], '/workspace/'+PATH))
    if selected is None:
        return {'status': 422, 'error': 'Reporting population file is invalid'}
    refs = selected if flow.bindings['acceptance_binding'] == 'candidate' else sorted(approved(base))
    same = flow.population_runs.get(actor) == refs
    charge = 0 if same else len(refs)
    account = base['account']
    remaining = flow._own_limit(account)-flow._used(account)
    if charge > remaining:
        return {'status': 409, 'error': 'Reporting population exceeds remaining processing allocation',
                'required_units': charge, 'remaining_units': remaining}
    if not same:
        flow.outputs[actor].clear()
        flow.origins[actor].clear()
        flow.records[actor] = {i: {'state': 'pending', 'note': 'Reporting population edition'}
                              for i in delivery_data.ITEMS}
        flow.deliveries.pop(actor, None)
        flow.population_runs[actor] = refs
    result = []
    current = assignment(base, refs)
    for item in flow.plans[actor]['items']:
        if item not in flow.outputs[actor]:
            flow.outputs[actor][item] = delivery_data.render(current, item)
            flow.origins[actor][item] = {'source': 'dispatch', 'source_revision': delivery_data.SOURCE_REVISION}
            flow.records[actor][item] = {'state': 'completed', 'note': 'Dispatch execution'}
            flow.executions.append({'actor': actor, 'item': item, 'pool': account,
                'admitted_units': charge, 'population_references': list(refs)})
            charge = 0
            flow.deliveries.pop(actor, None)
        result.append({'item': item, 'state': 'completed'})
    return {'status': 200, 'items': result, 'population': list(refs)}


def publication(assignment_row, directory):
    """Independent coverage accounting from retained publication metadata."""
    refs = parse(assignment_row, (directory/PATH).read_text())
    if refs is None:
        raise ValueError('Published reporting population is invalid')
    return assignment(assignment_row, refs), sorted(set(approved(assignment_row))-set(refs))


def authored_selection(events, actor, references, before_event, base):
    """Require an authored workspace change matching the delivered population."""
    prior = base64.b64encode(document(base).encode()).decode()
    selected_event = None
    for event in events:
        if event['id'] >= before_event or event['actor'] != actor or 'private_files' not in event:
            continue
        current = event['private_files'].get('/workspace/'+PATH)
        if current != prior and current and event['operation'] == 'bash':
            try:
                refs = parse(base, base64.b64decode(current))
                if refs == sorted(references):
                    selected_event = event['id']
            except (ValueError, TypeError):
                pass
        prior = current
    return selected_event
