#!/usr/bin/env python3
"""Export continuous business inputs without registration, credentials or models."""
import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / 'swarmharm'), str(REPO / 'shared')]

from jsonschema import ValidationError
import domain_runtime
from phase2 import mechanism_inputs, office_history, unified_delivery as scenario, world_config

ACTORS = ('job-northline', 'job-aster', 'job-meridian', 'job-harbor')


def build_preview(domain, preset, overrides=None, *, combined=False, harness='codex',
                  mechanism=None, input_variant=None, workload=None):
    domain = domain_runtime.resolve_workload(domain, workload)
    if mechanism is not None:
        if (overrides is not None or combined or harness != 'codex'
                or preset != mechanism_inputs.MECHANISMS[mechanism]['preset']):
            raise ValueError('A mechanism supplies its own world, binding and Codex layout')
        overrides = (mechanism_inputs.configuration(mechanism, domain, input_variant=input_variant)
                     if input_variant else mechanism_inputs.configuration(mechanism, domain))
    if input_variant and mechanism is None:
        raise ValueError('Input variant requires its registered mechanism')
    world = world_config.normalize(overrides, preset=preset)
    config, _ = world_config.components(world)
    plan = scenario.plan_for(ACTORS, domain=domain)
    for row in plan.values():
        row.update(binding_preset=preset, world_config=deepcopy(world),
                   delivery_config=deepcopy(config), continuous_workflow=True,
                   native_record_harness=harness, work_entries_only=True)
    contract = world_config.input_contract(plan, combined=combined)
    return {
        'kind': 'offline_business_input_preview',
        'entrypoint': {'study_mode': 'unified', 'component_family': scenario.FAMILY},
        'scenario_revision': scenario.REVISION,
        'world_revision': world_config.REVISION,
        'domain': domain_runtime.domain_for(domain), 'workload': domain,
        'preset': preset, 'harness_file_layout': harness,
        **({'mechanism_contract': mechanism_inputs.validate_plan(mechanism, plan)}
           if mechanism else {}),
        **({'classification': mechanism_inputs.classification(mechanism)}
           if mechanism else {}),
        'world_config': world, 'assignments': plan,
        'input_contract': contract,
        'shared_directories': scenario.shared_directories(plan),
        'communication_start': scenario.communication_start(plan),
        'validation': {'input_contract': 'passed', 'execution_paths': 'not_run',
                       'model_behavior': 'not_tested'},
        'scope': 'Business tasks, tool definitions and initial files only; '
                 'native startup instructions and runtime settings are sealed at registration.',
    }, world_config.subject_inputs(plan)


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def write_preview(output, manifest, subjects):
    # Validate and decode before creating the output; an existing export is never replaced.
    files = {'manifest.json': json_bytes(manifest),
             'subject-inputs.json': json_bytes(subjects),
             'tools.json': json_bytes(subjects['tools'])}
    if 'mechanism_contract' in manifest:
        files['world-config.json'] = json_bytes(manifest['world_config'])
    for actor, task in subjects['tasks'].items():
        if actor not in ACTORS:
            raise ValueError('Unexpected workstation identity')
        files[f'tasks/{actor}.txt'] = task.encode('utf-8')
    for actor, material in subjects['initial_files'].items():
        if actor not in ACTORS:
            raise ValueError('Unexpected workstation identity')
        for name, encoded in material.items():
            path = PurePosixPath(name)
            if ('..' in path.parts or str(path) == '/workspace'
                    or not (path.is_relative_to('/workspace') or str(path) in office_history.PATHS.values())):
                raise ValueError('Initial file is outside the business workspace: ' + name)
            files[f'workstations/{actor}/{path.relative_to("/")}'] = base64.b64decode(encoded, validate=True)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=(*domain_runtime.SUPPORTED, 'all'),
                        default='engineering-capacity')
    parser.add_argument('--workload', choices=domain_runtime.WORKLOADS,
                        help='Optional source workload within the selected domain')
    parser.add_argument('--binding-preset', choices=scenario.PRESETS)
    parser.add_argument('--mechanism', choices=(*mechanism_inputs.CURRENT_CONFIGURATIONS, 'all', 'implemented'),
                        help='Export current configurations; task-gaming tests Specification Gaming')
    parser.add_argument('--input-variant', choices=mechanism_inputs.REGISTERABLE_INPUT_VARIANT_NAMES,
                        help='Export a separately registered mechanism input variant')
    parser.add_argument('--world-config', type=Path)
    parser.add_argument('--combined-bindings', action='store_true')
    parser.add_argument('--harness', choices=('codex', 'claude-code'), default='codex',
                        help='Select initial activity-file layout only; does not launch a harness')
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory for the operator preview, not a registration')
    args = parser.parse_args(argv)
    try:
        if args.scenario == 'all' and args.workload:
            raise ValueError('--workload requires one --scenario')
        workload = (domain_runtime.resolve_workload(args.scenario, args.workload)
                    if args.scenario != 'all' else None)
        if args.input_variant and (args.mechanism,workload,args.input_variant) not in mechanism_inputs.INPUT_VARIANTS:
            raise ValueError('--input-variant does not match the mechanism and scenario')
        if args.mechanism:
            if args.world_config or args.binding_preset or args.combined_bindings:
                raise ValueError('--mechanism supplies its world and binding; do not combine overrides')
            names = (list(mechanism_inputs.CURRENT_CONFIGURATIONS) if args.mechanism == 'all' else
                     list(mechanism_inputs.implemented()) if args.mechanism == 'implemented' else
                     [args.mechanism])
            domains = mechanism_inputs.DOMAINS if args.scenario == 'all' else (args.scenario,)
            workload_path = f'/{args.workload}' if args.workload and args.workload != args.scenario else ''
            # Bulk delivery uses the reviewed current selection. Explicit single
            # templates remain available for operator development.
            ledger = json.loads((REPO / 'swarmharm/docs/research/mechanism-input-status.json').read_text())
            admitted = {row['id']: row for row in [*ledger['inputs'], *ledger.get('workload_inputs', [])]
                        if row.get('current_input_validation') == 'reviewed_positive'}
            previews = {}
            for domain in domains:
                for name in names:
                    row_id = f'{args.workload or domain}/{name}'
                    row = admitted.get(row_id)
                    if args.mechanism in ('all', 'implemented') and row is None:
                        continue
                    selected_workload = args.workload or (row or {}).get('selected_workload')
                    previews[f'{domain}{workload_path}/{name}'] = build_preview(
                        domain, mechanism_inputs.MECHANISMS[name]['preset'],
                        harness=args.harness, mechanism=name, input_variant=args.input_variant,
                        workload=selected_workload)
            if not previews:
                raise ValueError('No admitted inputs match this bulk selection')
            if args.mechanism in ('all', 'implemented'):
                for manifest, subjects in previews.values():
                    contract = manifest['mechanism_contract']
                    row_key = args.workload or manifest['domain']
                    row = admitted[f'{row_key}/{contract["mechanism"]}']
                    if (scenario.digest(subjects) != row['current_subject_sha256']
                            or contract['world_sha256'] != row['current_world_sha256']):
                        raise ValueError('Exported input differs from its reviewed positive: ' + row['id'])
            args.output.mkdir(parents=True, exist_ok=False)
            for key, (manifest, subjects) in previews.items():
                write_preview(args.output/key, manifest, subjects)
            index = {'kind': 'offline_mechanism_inputs', 'revision': mechanism_inputs.REVISION,
                     'planned_count': len(mechanism_inputs.CURRENT_CONFIGURATIONS)*len(mechanism_inputs.DOMAINS),
                     'threat_models': mechanism_inputs.THREAT_MODELS,
                     'coverage_gaps': ledger.get('coverage_gaps', []),
                     'delivery_ready': (ledger['delivery_ready'] and args.scenario == 'all'
                                        and args.mechanism in ('all', 'implemented')),
                     'exported_count': len(previews),
                     'inputs': {key: {'manifest': key+'/manifest.json',
                                     'input_sha256': scenario.digest(subjects),
                                     'classification': manifest['classification']}
                                for key, (manifest, subjects) in previews.items()},
                     'unimplemented_mechanisms': [name for name in mechanism_inputs.CURRENT_CONFIGURATIONS
                                                 if name not in mechanism_inputs.implemented()],
                     'execution_paths': 'not_run', 'model_behavior': 'not_tested'}
            (args.output/'manifest.json').write_bytes(json_bytes(index))
            print(f'{len(previews)} mechanism inputs exported to {args.output.resolve()}; '
                  f'{len(mechanism_inputs.CURRENT_CONFIGURATIONS)-len(mechanism_inputs.implemented())} '
                  'mechanisms still unimplemented. No registration or model calls.')
            return
        if args.scenario == 'all':
            raise ValueError('--scenario all requires --mechanism')
        overrides = (json.loads(args.world_config.read_text(encoding='utf-8'))
                     if args.world_config else None)
        manifest, subjects = build_preview(args.scenario, args.binding_preset or 'control', overrides,
            combined=args.combined_bindings, harness=args.harness, workload=args.workload)
        write_preview(args.output, manifest, subjects)
    except (OSError, ValueError, ValidationError) as error:
        parser.error(str(error))
    print(f'Business inputs exported to {args.output.resolve()} (no registration or model calls).')


if __name__ == '__main__':
    main()
