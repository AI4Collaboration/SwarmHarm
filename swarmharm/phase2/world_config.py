"""Canonical four-group input for the unified reporting environment."""
from copy import deepcopy
from phase2 import office_history

REVISION = 'reporting-world-v9'


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
                         'capacity_basis': bindings['capacity_binding'],
                         'completion_evidence': bindings['evidence_binding'],
                         'grader_source': bindings['grader_binding'],
                         'descriptor_delivery': cfg['descriptor_delivery'],
                         'catalog_schema': cfg['catalog_schema'],
                         'completion_basis': cfg['completion_basis']},
        'observation': {key: cfg[key] for key in ('feedback', 'status_scope', 'status_refresh_seconds', 'receipt_scope')},
    }
    optional_observations = (office_history.FIELD, 'workstation_processes', 'notification_scope', 'notification_detail', 'work_file_index', 'activity_scope')
    for field in optional_observations:
        if field in cfg:
            result['observation'][field] = cfg[field]
    if 'forecast_deliverable' in cfg:
        result['verification']['forecast_deliverable'] = cfg['forecast_deliverable']
    if 'native_evidence_accounts' in cfg:
        result['verification']['native_evidence_accounts'] = cfg['native_evidence_accounts']
    if 'closeout_record' in cfg:
        result['verification']['closeout_record'] = cfg['closeout_record']
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
            'capacity_basis': {'enum': ['approved', 'forecast']},
            'completion_evidence': {'enum': ['executed', 'register', 'native']},
            'native_evidence_accounts': deepcopy(scenario.CONFIG_SCHEMA['properties']['native_evidence_accounts']),
            'grader_source': {'enum': ['installed', 'workspace']},
            'descriptor_delivery': deepcopy(scenario.CONFIG_SCHEMA['properties']['descriptor_delivery']),
            'catalog_schema': deepcopy(scenario.CONFIG_SCHEMA['properties']['catalog_schema']),
            'forecast_deliverable': deepcopy(scenario.CONFIG_SCHEMA['properties']['forecast_deliverable']),
            'closeout_record': deepcopy(scenario.CONFIG_SCHEMA['properties']['closeout_record']),
            'completion_basis': {'enum': ['dispatch', 'contents', 'handoff']}}},
        'observation': {'type': 'object', 'additionalProperties': False, 'properties': {
            key: deepcopy(scenario.CONFIG_SCHEMA['properties'][key])
            for key in ('feedback', 'status_scope', 'status_refresh_seconds', 'receipt_scope', *optional_observations)}},
    }}
    Draft202012Validator(schema).validate({} if value is None else value)
    for group, settings in (value or {}).items():
        result[group].update(settings)
    return result


def components(world):
    """Compile into existing business controls without a second interpretation."""
    access, coupling, verification, observation = (world[key]
        for key in ('access', 'coupling', 'verification', 'observation'))
    config = {'access': {key: access[key] for key in (
                  'plan', 'register', 'report_upload', 'dispatch_input', 'forecast_workflow', 'account_slots', 'library_gateway', 'reserve_use', 'library_edition', 'source_exports')
                  if key in access},
              'sharing': {key: coupling[key] for key in ('resource_pool', 'discussion',
                                                       'published_packs', 'completion_credit',
                                                       'source_routing', 'communication_format', 'note_readers')
                          if key in coupling},
              'operations_headroom': coupling['operations_headroom'],
              'completion_basis': verification['completion_basis'],
              'descriptor_delivery': verification['descriptor_delivery'],
              'catalog_schema': verification.get('catalog_schema', 'independent'), **observation}
    if 'forecast_deliverable' in verification:
        config['forecast_deliverable'] = verification['forecast_deliverable']
    if 'native_evidence_accounts' in verification:
        config['native_evidence_accounts'] = verification['native_evidence_accounts']
    if 'closeout_record' in verification:
        config['closeout_record'] = verification['closeout_record']
    bindings = {'resource_binding': access['pool_scope'], 'information_binding': access['information_scope'],
                'capacity_binding': verification.get('capacity_basis', 'approved'),
                'acceptance_binding': verification['required_items'],
                'evidence_binding': verification['completion_evidence'],
                'grader_binding': verification['grader_source']}
    return deepcopy(config), deepcopy(bindings)


def selection(world, preset, *, combined=False):
    """Declare which interfaces vary in this one rollout; operator-only."""
    from phase2 import unified_delivery as scenario
    _, bindings = components(normalize(world))
    baseline = scenario.PRESETS['control']
    changed = {key: {'baseline': baseline[key], 'selected': value}
               for key, value in bindings.items() if value != baseline[key]}
    if len(changed) > 1 and not combined:
        raise ValueError('Multiple evaluated bindings require --combined-bindings; '
                         'run threat models separately by default')
    if combined and len(changed) < 2:
        raise ValueError('--combined-bindings requires at least two changed bindings')
    if not combined and bindings != scenario.PRESETS[preset]:
        raise ValueError('World bindings do not match the selected preset; '
                         'select the preset for this interface')
    return {'mode': 'combined' if combined else 'single' if changed else 'baseline',
            'requested_preset': preset,
            'matches_named_preset': bindings == scenario.PRESETS[preset],
            'changed_bindings': changed,
            'combination_explicit': combined}


def subject_inputs(plan):
    """Business input bytes shared by registration checks and offline inspection."""
    from phase2 import unified_delivery as scenario
    config = scenario.config_for(plan)
    return {'tasks': {actor: scenario.task(row) for actor, row in plan.items()},
            'tools': scenario.tool_definitions(
                continuous_workflow=bool(next(iter(plan.values())).get('continuous_workflow')),
                forecast_workflow=config['access']['forecast_workflow'],
                source_routing=config['sharing']['source_routing'],
                catalog_schema=config.get('catalog_schema', 'independent')),
            'initial_files': scenario.initial_files(plan),
            'business_data': {actor: scenario.delivery_data.source_data(row)
                              for actor, row in plan.items()}}


def input_contract(plan, *, combined=False):
    """Verify the same subject input at fixed business settings, not just assert it."""
    from phase2 import unified_delivery as scenario
    world = scenario.world_for(plan)
    chosen = selection(world, scenario.preset_for(plan), combined=combined)
    config = scenario.config_for(plan)
    reference = deepcopy(plan)
    for assignment in reference.values():
        assignment.update(binding_preset='control', delivery_config=deepcopy(config),
                          world_config=normalize(preset='control', delivery=config))

    actual, expected = subject_inputs(plan), subject_inputs(reference)
    if actual != expected:
        changed = [name for name in actual if actual[name] != expected[name]]
        raise ValueError('Binding selection changes shared subject inputs: ' + ', '.join(changed))
    return {'revision': 'unified-input-contract-v1',
            'selection': chosen,
            'world_sha256': scenario.digest(world),
            'domain': scenario.delivery_data.domain_for(next(iter(plan.values()))),
            'subject_sha256': {name: scenario.digest(value) for name, value in actual.items()},
            'matched_baseline_subject_inputs': True,
            'execution': 'one independent rollout of one normalized world configuration',
            'findings_are_observations_not_subject_instructions': True}


def verify_input_contract(plan, registered):
    if not isinstance(registered, dict):
        raise ValueError('Missing unified input contract; prepare a fresh registration')
    combined = registered.get('selection', {}).get('combination_explicit')
    if type(combined) is not bool or registered != input_contract(plan, combined=combined):
        raise ValueError('Registered unified input contract differs; prepare fresh inputs')
