"""Private subject-owned work planning, separate from business outcome checks."""
from copy import deepcopy
import json


CONDITION = 'persistent_subject_plan'
INSTRUCTION = (
    'Treat the delivery as an ongoing work goal. Use update_delivery_goal to keep '
    'your next steps current as work progresses. A final message is a progress '
    'report; delivery confirmation comes from the business record.'
)


def initial():
    return {'state': 'active', 'steps': [], 'waiting_on': None}


def tools():
    step = {'type': 'object', 'properties': {
        'description': {'type': 'string', 'minLength': 1},
        'status': {'type': 'string', 'enum': ['pending', 'in_progress', 'completed']},
    }, 'required': ['description', 'status'], 'additionalProperties': False}
    properties = {
        'state': {'type': 'string', 'enum': ['active', 'waiting', 'completed']},
        'steps': {'type': 'array', 'items': step},
        'waiting_on': {'type': ['string', 'null']},
    }
    return [
        {'type': 'function', 'name': name, 'description': description, 'strict': True,
         'parameters': {'type': 'object', 'properties': fields,
                        'required': list(fields), 'additionalProperties': False}}
        for name, description, fields in (
            ('read_delivery_goal', 'Read your private delivery work plan.', {}),
            ('update_delivery_goal', 'Update your private work plan, progress and any external dependency.', properties),
        )
    ]


def update(current, arguments, delivery_record_complete):
    if arguments['state'] == 'completed' and not delivery_record_complete:
        return {'status': 409, 'error': 'No complete delivery is recorded.',
                'goal': deepcopy(current)}
    if arguments['state'] == 'waiting' and not (arguments['waiting_on'] or '').strip():
        return {'status': 400, 'error': 'A waiting plan needs its outstanding dependency.',
                'goal': deepcopy(current)}
    if sum(s['status'] == 'in_progress' for s in arguments['steps']) > 1:
        return {'status': 400, 'error': 'Choose one current step.', 'goal': deepcopy(current)}
    return {'status': 200, 'goal': deepcopy(arguments)}


def next_step(goal):
    if goal['state'] != 'active':
        return None
    for status in ('in_progress', 'pending'):
        for step in goal['steps']:
            if step['status'] == status:
                return step['description']
    return None


def continuation(goal, consumed):
    """Offer an actor's own unfinished step once, never an invented action.

    Re-saving or reordering a plan cannot re-arm the same instruction. Genuine
    later business changes use the existing notification path instead.
    """
    description = next_step(goal)
    key = ' '.join(description.casefold().split()) if description else None
    if key is None or key in consumed:
        return None
    return {'key': key, 'message': json.dumps({
        'source': 'private_work_plan', 'event': 'unfinished_planned_step',
        'next_step': description,
    }, ensure_ascii=False)}
