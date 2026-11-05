"""Canonical four-group input for the unified reporting environment."""
from copy import deepcopy

REVISION = 'reporting-world-v1'


def normalize(value=None, *, preset='control', delivery=None):
    from jsonschema import Draft202012Validator
    from phase2 import unified_delivery as scenario
    if value is not None and delivery is not None:
        raise ValueError('Choose world-config or delivery-config, not both')
    cfg = scenario.normalize_config(delivery)
    bindings = scenario.PRESETS[preset]
    result = {
        'access': {**cfg['access'], 'pool_scope': bindings['resource_binding'],
                   'information_scope': bindings['information_binding']},
        'coupling': {**cfg['sharing'], 'operations_headroom': cfg['operations_headroom']},
        'verification': {'required_items': bindings['acceptance_binding'],
                         'completion_evidence': bindings['evidence_binding'],
                         'grader_source': bindings['grader_binding'],
                         'completion_basis': cfg['completion_basis']},
        'observation': {key: cfg[key] for key in ('feedback', 'status_scope', 'status_refresh_seconds')},
    }
    schema = {'type': 'object', 'additionalProperties': False, 'properties': {
        'access': {'type': 'object', 'additionalProperties': False, 'properties': {
            **deepcopy(scenario.CONFIG_SCHEMA['properties']['access']['properties']),
            'pool_scope': {'enum': ['purpose', 'allocation']},
            'information_scope': {'enum': ['task', 'account']}}},
        'coupling': {'type': 'object', 'additionalProperties': False, 'properties': {
            **deepcopy(scenario.CONFIG_SCHEMA['properties']['sharing']['properties']),
            'operations_headroom': deepcopy(scenario.CONFIG_SCHEMA['properties']['operations_headroom'])}},
        'verification': {'type': 'object', 'additionalProperties': False, 'properties': {
            'required_items': {'enum': ['approved', 'candidate']},
            'completion_evidence': {'enum': ['executed', 'register', 'native']},
            'grader_source': {'enum': ['installed', 'workspace']},
            'completion_basis': {'enum': ['dispatch', 'contents']}}},
        'observation': {'type': 'object', 'additionalProperties': False, 'properties': {
            key: deepcopy(scenario.CONFIG_SCHEMA['properties'][key])
            for key in ('feedback', 'status_scope', 'status_refresh_seconds')}},
    }}
    Draft202012Validator(schema).validate({} if value is None else value)
    for group, settings in (value or {}).items():
        result[group].update(settings)
    return result


def components(world):
    """Compile into existing business controls without a second interpretation."""
    access, coupling, verification, observation = (world[key]
        for key in ('access', 'coupling', 'verification', 'observation'))
    config = {'access': {key: access[key] for key in ('plan', 'register', 'report_upload')},
              'sharing': {key: coupling[key] for key in ('resource_pool', 'discussion',
                                                       'published_packs', 'completion_credit')},
              'operations_headroom': coupling['operations_headroom'],
              'completion_basis': verification['completion_basis'], **observation}
    bindings = {'resource_binding': access['pool_scope'], 'information_binding': access['information_scope'],
                'acceptance_binding': verification['required_items'],
                'evidence_binding': verification['completion_evidence'],
                'grader_binding': verification['grader_source']}
    return deepcopy(config), deepcopy(bindings)
