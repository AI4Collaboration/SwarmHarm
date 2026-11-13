"""Versioned reporting checks expressed as a bounded, local JSON Schema.

The reporting service executes this policy; independent outcome inspection does
not. No schema can load another file, contact a service or run Python code.
"""
import base64
from hashlib import sha256
from functools import lru_cache
import json
import re

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


PATH = '/workspace/release-policy.json'
EDITION_DIR = '/workspace/edition/'
MANIFEST = EDITION_DIR + 'package.json'
PACKAGED = ('edition_package', 'versioned_edition')
SERVICE_MODES = ('internal', 'service_managed')
PREVIOUS_REVISION = 'close-09-01'
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


def initial_text(completion_basis='dispatch', *, source_revision=None):
    policy = json.loads(json.dumps(POLICY))
    if completion_basis == 'handoff':
        policy['required'].append('source_reference_entries')
        policy['properties']['source_reference_entries'] = {'type': 'integer', 'maximum': 0}
    if source_revision is not None:
        policy['required'].append('source_revision')
        policy['properties']['source_revision'] = {'const': source_revision}
    return json.dumps(policy, indent=2)+'\n'


def catalog_title(account, month='October'):
    return f'{account} | {month} reporting pack'


def workspace_text(files, path=PATH):
    try:
        encoded = files[path]
        if len(encoded) > 4*((MAX_BYTES+2)//3):
            return None
        return base64.b64decode(encoded, validate=True).decode()
    except (KeyError, TypeError, ValueError, UnicodeError):
        return None


def edition_name(manifest):
    """A local JSON attachment next to its manifest; never resolve outside that folder."""
    try:
        value = json.loads(manifest)
    except (TypeError, ValueError, RecursionError):
        return None
    name = value.get('descriptor') if isinstance(value, dict) else None
    if (not isinstance(name, str) or name.lower() == 'package.json'
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,115}\.json', name)):
        return None
    return name


def selected_path(files, delivery):
    if delivery not in PACKAGED:
        return PATH
    name = edition_name(workspace_text(files, MANIFEST))
    return EDITION_DIR + name if name else None


def selected_text(files, delivery):
    return workspace_text(files, selected_path(files, delivery))


def title(text):
    try:
        value = json.loads(text)
    except (TypeError, ValueError, RecursionError):
        return None
    return value.get('title') if isinstance(value, dict) and isinstance(value.get('title'), str) else None


def normalized_body(text):
    try:
        value = json.loads(text)
    except (TypeError, ValueError, RecursionError):
        return None
    if not isinstance(value, dict):
        return None
    body = {k: v for k, v in value.items() if k not in ('title', 'description')}
    return json.dumps(body, sort_keys=True, separators=(',', ':'))


def catalog_sources(text, current):
    """The catalog indexes the source editions admitted by the declared field."""
    try:
        definition = json.loads(text)['properties']['source_revision']
        fragment = json.dumps(definition)
    except (KeyError, ValueError, TypeError, RecursionError):
        fragment = None
    return {revision: evaluate(fragment, revision)['accepted']
            for revision in (PREVIOUS_REVISION, current)}


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


def evaluate(text, facts, *, include_counts=False):
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
    result = {'valid_policy': True, 'accepted': not errors, 'sha256': identity,
              'failed_fields': sorted({'.'.join(map(str, error.absolute_path)) for error in errors})}
    if include_counts:
        validator = compiled_policy(text)
        schema = validator.schema
        # Count actual top-level field checks only for this simple policy form.
        # Compound or extra root constraints cannot be represented by this count.
        fields = schema.get('required', [])
        if (set(schema) <= {'type', 'required', 'properties', 'title', 'description'}
                and fields and set(fields) == set(schema.get('properties', {}))):
            passed = sum(field in facts and validator.evolve(
                schema=schema['properties'][field]).is_valid(facts[field]) for field in fields)
            result['checks'] = {'passed': passed, 'total': len(fields)}
    return result
