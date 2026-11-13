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
                   'information_scope': bindings['information_binding'],
                   'operation_scope': bindings['operation_binding']},
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
    if 'meter_binding' in bindings:
        result['verification']['quota_meter'] = bindings['meter_binding']
    if ('lifecycle_binding' in bindings or cfg['access'].get('job_scope') == 'shared_window'
            or cfg['access'].get('worker_recovery') == 'enabled'
            or cfg['access'].get('retention_store') in ('enabled', 'knowledge', 'engineering')
            or cfg['access'].get('payables_workflow') in ('enabled', 'timed', 'timed-v2')):
        result['verification']['job_lifecycle'] = bindings.get('lifecycle_binding', 'required')
    optional_observations = (office_history.FIELD, 'workstation_processes', 'notification_scope', 'notification_detail', 'work_file_index', 'activity_scope', 'library_metadata', 'library_navigation', 'library_guide', 'library_connections', 'preview_records', 'check_summary', 'budget_view')
    for field in optional_observations:
        if field in cfg:
            result['observation'][field] = cfg[field]
    if 'forecast_deliverable' in cfg:
        result['verification']['forecast_deliverable'] = cfg['forecast_deliverable']
    if 'native_evidence_accounts' in cfg:
        result['verification']['native_evidence_accounts'] = cfg['native_evidence_accounts']
    if 'closeout_record' in cfg:
        result['verification']['closeout_record'] = cfg['closeout_record']
    if 'cost_objective' in cfg:
        result['verification']['cost_objective'] = cfg['cost_objective']
    if 'publication_items' in cfg:
        result['verification']['publication_items'] = cfg['publication_items']
    if 'production_receipts' in cfg:
        result['verification']['production_receipts'] = cfg['production_receipts']
    schema = {'type': 'object', 'additionalProperties': False, 'properties': {
        'access': {'type': 'object', 'additionalProperties': False, 'properties': {
            **deepcopy(scenario.CONFIG_SCHEMA['properties']['access']['properties']),
            'pool_scope': {'enum': ['purpose', 'allocation']},
            'information_scope': {'enum': ['task', 'account']},
            'operation_scope': {'enum': ['owner', 'portfolio']}}},
        'coupling': {'type': 'object', 'additionalProperties': False, 'properties': {
            **deepcopy(scenario.CONFIG_SCHEMA['properties']['sharing']['properties']),
            'operations_headroom': deepcopy(scenario.CONFIG_SCHEMA['properties']['operations_headroom'])}},
        'verification': {'type': 'object', 'additionalProperties': False, 'properties': {
            'required_items': {'enum': ['approved', 'candidate']},
            'capacity_basis': {'enum': ['approved', 'forecast']},
            'quota_meter': {'enum': ['report', 'request']},
            'job_lifecycle': {'enum': ['required', 'mutable']},
            'completion_evidence': {'enum': ['executed', 'register', 'native', 'contents']},
            'native_evidence_accounts': deepcopy(scenario.CONFIG_SCHEMA['properties']['native_evidence_accounts']),
            'grader_source': {'enum': ['installed', 'workspace']},
            'descriptor_delivery': deepcopy(scenario.CONFIG_SCHEMA['properties']['descriptor_delivery']),
            'catalog_schema': deepcopy(scenario.CONFIG_SCHEMA['properties']['catalog_schema']),
            'forecast_deliverable': deepcopy(scenario.CONFIG_SCHEMA['properties']['forecast_deliverable']),
            'closeout_record': deepcopy(scenario.CONFIG_SCHEMA['properties']['closeout_record']),
            'cost_objective': deepcopy(scenario.CONFIG_SCHEMA['properties']['cost_objective']),
            'production_receipts': deepcopy(scenario.CONFIG_SCHEMA['properties']['production_receipts']),
            'publication_items': deepcopy(scenario.CONFIG_SCHEMA['properties']['publication_items']),
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
                  'plan', 'register', 'report_upload', 'dispatch_input', 'dispatch_batching', 'forecast_workflow', 'account_slots', 'library_gateway', 'reserve_use', 'charge_basis', 'library_edition', 'source_exports', 'source_record_counts', 'report_drafts', 'operations_workflow', 'allocation_layout', 'job_layout', 'population_plan', 'job_scope', 'cost_visibility', 'analytics_snapshot', 'quality_workflow', 'worker_recovery', 'retention_store', 'build_record_workflow', 'reconciliation_workflow', 'activity_report_workflow', 'payables_workflow', 'editorial_brief_workflow')
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
    if 'cost_objective' in verification:
        config['cost_objective'] = verification['cost_objective']
    if 'publication_items' in verification:
        config['publication_items'] = verification['publication_items']
    if 'production_receipts' in verification:
        config['production_receipts'] = verification['production_receipts']
    bindings = {'resource_binding': access['pool_scope'], 'information_binding': access['information_scope'],
                'capacity_binding': verification.get('capacity_basis', 'approved'),
                'operation_binding': access.get('operation_scope', 'owner'),
                'acceptance_binding': verification['required_items'],
                'evidence_binding': verification['completion_evidence'],
                'grader_binding': verification['grader_source']}
    if 'quota_meter' in verification:
        bindings['meter_binding'] = verification['quota_meter']
    if 'job_lifecycle' in verification:
        bindings['lifecycle_binding'] = verification['job_lifecycle']
    return deepcopy(config), deepcopy(bindings)


def selection(world, preset, *, combined=False):
    """Declare which interfaces vary in this one rollout; operator-only."""
    from phase2 import unified_delivery as scenario
    _, bindings = components(normalize(world))
    baseline = {**scenario.PRESETS['control'], **(
        {'meter_binding': 'report'} if 'meter_binding' in bindings else {}), **(
        {'lifecycle_binding': 'required'} if 'lifecycle_binding' in bindings else {})}
    expected = baseline if preset == 'control' else scenario.PRESETS[preset]
    changed = {key: {'baseline': baseline[key], 'selected': value}
               for key, value in bindings.items() if value != baseline[key]}
    if len(changed) > 1 and not combined:
        raise ValueError('Multiple evaluated bindings require --combined-bindings; '
                         'run threat models separately by default')
    if combined and len(changed) < 2:
        raise ValueError('--combined-bindings requires at least two changed bindings')
    if not combined and bindings != expected:
        raise ValueError('World bindings do not match the selected preset; '
                         'select the preset for this interface')
    return {'mode': 'combined' if combined else 'single' if changed else 'baseline',
            'requested_preset': preset,
            'matches_named_preset': bindings == expected,
            'changed_bindings': changed,
            'combination_explicit': combined}


def subject_inputs(plan):
    """Business input bytes shared by registration checks and offline inspection."""
    from phase2 import unified_delivery as scenario
    config = scenario.config_for(plan)
    return {'tasks': {actor: scenario.task(row) for actor, row in plan.items()},
            'tools': scenario.tool_definitions(
                continuous_workflow=bool(next(iter(plan.values())).get('continuous_workflow')),
                build_record_workflow=scenario.build_record_workflow(next(iter(plan.values()))),
                build_target_workflow=scenario.build_target_workflow(next(iter(plan.values()))),
                build_target_clarify_selection=scenario.build_target_clarify_selection(next(iter(plan.values()))),
                activity_report_workflow=scenario.activity_report_workflow(next(iter(plan.values()))),
                editorial_brief_workflow=scenario.editorial_brief_workflow(next(iter(plan.values()))),
                editorial_intake_archive=scenario.editorial_intake_archive(next(iter(plan.values()))),
                editorial_publication_index=scenario.editorial_publication_index(next(iter(plan.values()))),
                editorial_review_queue=scenario.editorial_review_queue(next(iter(plan.values()))),
                forecast_workflow=config['access']['forecast_workflow'],
                source_routing=config['sharing']['source_routing'],
                catalog_schema=config.get('catalog_schema', 'independent'),
                operations_workflow=config['access'].get('operations_workflow', 'none'),
                quality_workflow=config['access'].get('quality_workflow', 'disabled'),
                dispatch_batching=config['access'].get('dispatch_batching', 'disabled'),
                worker_recovery=config['access'].get('worker_recovery', 'disabled'),
                retention_store=config['access'].get('retention_store', 'disabled'),
                report_upload=config['access']['report_upload'],
                publication_items=config.get('publication_items', 'available'),
                population_plan=config['access'].get('population_plan', 'approved'),
                reconciliation_workflow=config['access'].get('reconciliation_workflow', 'disabled'),
                payables_workflow=config['access'].get('payables_workflow', 'disabled')),
            'initial_files': scenario.initial_files(plan),
            'business_data': (scenario.truth_for(plan)['accounts'] if config['access'].get('payables_workflow') in ('enabled', 'timed', 'timed-v2') else
                {actor: {'request_id':scenario.delivery_reconciliation.REQUESTS[row['account']],
                 'approved_period':scenario.delivery_reconciliation.APPROVED,
                 'source_periods':list(scenario.delivery_reconciliation.PERIODS)} for actor,row in plan.items()}
                if config['access'].get('reconciliation_workflow') in ('enabled', 'exception-context', 'category-template') else
                scenario.truth_for(plan)['accounts'] if (scenario.build_record_workflow(next(iter(plan.values()))) or scenario.activity_report_workflow(next(iter(plan.values()))) or scenario.editorial_brief_workflow(next(iter(plan.values())))) else
                {actor: scenario.delivery_data.source_data(row) for actor, row in plan.items()})}


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
