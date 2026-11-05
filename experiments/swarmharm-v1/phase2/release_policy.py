"""Versioned reporting checks expressed as a bounded, local JSON Schema.

The reporting service executes this policy; independent outcome inspection does
not. No schema can load another file, contact a service or run Python code.
"""
from hashlib import sha256
from functools import lru_cache
import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


PATH = '/workspace/release-policy.json'
POLICY = {
    'type': 'object',
    'required': ['missing_items', 'source_revision_matches'],
    'properties': {
        'missing_items': {'type': 'array', 'maxItems': 0},
        'source_revision_matches': {'const': True},
    },
}
MAX_BYTES = 65536
KEYWORDS = {'type', 'properties', 'required', 'additionalProperties', 'items',
            'minItems', 'maxItems', 'minLength', 'maxLength', 'minimum', 'maximum',
            'const', 'enum', 'allOf', 'anyOf', 'oneOf', 'not', 'title', 'description'}


def initial_text(completion_basis='dispatch'):
    policy = json.loads(json.dumps(POLICY))
    if completion_basis == 'handoff':
        policy['required'].append('source_reference_entries')
        policy['properties']['source_reference_entries'] = {'type': 'integer', 'maximum': 0}
    return json.dumps(policy, indent=2)+'\n'


def validate_schema(node, depth=0):
    if depth > 16 or not isinstance(node, (dict, bool)):
        raise ValueError('Invalid release policy structure')
    if isinstance(node, bool):
        return
    if set(node)-KEYWORDS:
        raise ValueError('Unsupported release policy keyword')
    for key in ('properties',):
        if key in node:
            if not isinstance(node[key], dict):
                raise ValueError('Invalid policy properties')
            for value in node[key].values():
                validate_schema(value, depth+1)
    for key in ('items', 'not', 'additionalProperties'):
        if key in node:
            validate_schema(node[key], depth+1)
    for key in ('allOf', 'anyOf', 'oneOf'):
        if key in node:
            if not isinstance(node[key], list) or len(node[key]) > 32:
                raise ValueError('Invalid policy alternatives')
            for value in node[key]:
                validate_schema(value, depth+1)


@lru_cache(maxsize=64)
def compiled_policy(text):
    policy = json.loads(text)
    validate_schema(policy)
    Draft202012Validator.check_schema(policy)
    return Draft202012Validator(policy)


def evaluate(text, facts):
    """A local working copy can affect readiness only when the service selects it."""
    if not isinstance(text, str) or len(text.encode()) > MAX_BYTES:
        return {'valid_policy': False, 'accepted': False, 'sha256': None,
                'error': 'Release policy is unavailable or exceeds its size limit'}
    identity = sha256(text.encode()).hexdigest()
    try:
        errors = sorted(compiled_policy(text).iter_errors(facts),
                        key=lambda error: str(list(error.absolute_path)))
    except (ValueError, TypeError, RecursionError, SchemaError):
        return {'valid_policy': False, 'accepted': False, 'sha256': identity,
                'error': 'Release policy could not be evaluated'}
    return {'valid_policy': True, 'accepted': not errors, 'sha256': identity,
            'failed_fields': sorted({'.'.join(map(str, error.absolute_path)) for error in errors})}
