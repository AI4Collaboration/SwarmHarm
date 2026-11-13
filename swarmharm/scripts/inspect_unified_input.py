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
from phase2 import mechanism_inputs, office_history, threat_grid, unified_delivery as scenario, world_config

ACTORS = ('job-northline', 'job-aster', 'job-meridian', 'job-harbor')


def build_preview(domain, preset, overrides=None, *, combined=False, harness='codex', cell=None,
                  mechanism=None, input_variant=None):
    if mechanism is not None:
        if (cell is not None or overrides is not None or combined or harness != 'codex'
                or preset != mechanism_inputs.MECHANISMS[mechanism]['preset']):
            raise ValueError('A mechanism supplies its own world, binding and Codex layout')
        overrides = (mechanism_inputs.configuration(mechanism, domain, input_variant=input_variant)
                     if input_variant else mechanism_inputs.configuration(mechanism, domain))
    if input_variant and mechanism is None:
        raise ValueError('Input variant requires its registered mechanism')
    if cell is not None:
        if overrides is not None or combined or preset != threat_grid.CELLS[cell]['preset']:
            raise ValueError('A threat cell supplies its own world and binding')
        overrides = threat_grid.configuration(cell)
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
        'domain': domain, 'preset': preset, 'harness_file_layout': harness,
        **({'threat_cell': {'cell': cell, **threat_grid.CELLS[cell],
                           'visibility': 'operator_only'}} if cell else {}),
        **({'mechanism_contract': mechanism_inputs.validate_plan(mechanism, plan)}
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
    parser.add_argument('--scenario', choices=(*scenario.delivery_data.DOMAINS, 'all'),
                        default='engineering-capacity')
    parser.add_argument('--binding-preset', choices=scenario.PRESETS)
    parser.add_argument('--threat-cell', choices=(*threat_grid.CELLS, 'all'),
                        help='Export archived grid inputs; no registration, checks or model calls')
    parser.add_argument('--mechanism', choices=(*mechanism_inputs.MECHANISMS, 'all', 'implemented'),
                        help='Export declared mechanism inputs; all requires every binding to be implemented')
    parser.add_argument('--input-variant', choices=('finance-exception-context-v1','finance-timed-settlement-v2','finance-timed-settlement-v1','data-worker-recovery-v1','data-progressive-processing-v1','data-progressive-varied-v2','data-progressive-context-v3','data-progressive-dictionary-v4','knowledge-intake-archive-v1','knowledge-publication-index-v1','knowledge-review-queue-v1','knowledge-review-context-v2','engineering-receipt-defined-v1','engineering-receipt-visible-v2'),
                        help='Export a separately registered mechanism input variant')
    parser.add_argument('--world-config', type=Path)
    parser.add_argument('--combined-bindings', action='store_true')
    parser.add_argument('--harness', choices=('codex', 'claude-code'), default='codex',
                        help='Select initial activity-file layout only; does not launch a harness')
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory for the operator preview, not a registration')
    args = parser.parse_args(argv)
    try:
        if args.input_variant and (args.mechanism,args.scenario,args.input_variant) not in (
                ('work-lifecycle','data-analysis','data-worker-recovery-v1'),
                ('target-substitution','financial-analysis','finance-exception-context-v1'),
                ('target-substitution','data-analysis','data-progressive-processing-v1'),
                ('target-substitution','data-analysis','data-progressive-varied-v2'),
                ('target-substitution','data-analysis','data-progressive-context-v3'),
                ('target-substitution','data-analysis','data-progressive-dictionary-v4'),
                ('work-lifecycle','financial-analysis','finance-timed-settlement-v1'),
                ('work-lifecycle','financial-analysis','finance-timed-settlement-v2'),
                ('evidence-tampering','engineering-capacity','engineering-receipt-defined-v1'),
                ('evidence-tampering','engineering-capacity','engineering-receipt-visible-v2'),
                ('target-substitution','knowledge-work','knowledge-intake-archive-v1'),
                ('target-substitution','knowledge-work','knowledge-publication-index-v1'),
                ('target-substitution','knowledge-work','knowledge-review-queue-v1'),
                ('target-substitution','knowledge-work','knowledge-review-context-v2')):
            raise ValueError('--input-variant does not match the mechanism and scenario')
        if args.mechanism:
            if args.threat_cell or args.world_config or args.binding_preset or args.combined_bindings:
                raise ValueError('--mechanism supplies its world and binding; do not combine overrides')
            names = (list(mechanism_inputs.MECHANISMS) if args.mechanism == 'all' else
                     list(mechanism_inputs.implemented()) if args.mechanism == 'implemented' else
                     [args.mechanism])
            domains = mechanism_inputs.DOMAINS if args.scenario == 'all' else (args.scenario,)
            previews = {f'{domain}/{name}': build_preview(domain,
                        mechanism_inputs.MECHANISMS[name]['preset'],
                        harness=args.harness, mechanism=name, input_variant=args.input_variant)
                        for domain in domains for name in names}
            args.output.mkdir(parents=True, exist_ok=False)
            for key, (manifest, subjects) in previews.items():
                write_preview(args.output/key, manifest, subjects)
            index = {'kind': 'offline_mechanism_inputs', 'revision': mechanism_inputs.REVISION,
                     'planned_count': len(mechanism_inputs.MECHANISMS)*len(mechanism_inputs.DOMAINS),
                     'exported_count': len(previews),
                     'inputs': {key: {'manifest': key+'/manifest.json',
                                     'input_sha256': scenario.digest(subjects)}
                                for key, (_, subjects) in previews.items()},
                     'unimplemented_mechanisms': [name for name in mechanism_inputs.MECHANISMS
                                                 if name not in mechanism_inputs.implemented()],
                     'execution_paths': 'not_run', 'model_behavior': 'not_tested'}
            (args.output/'manifest.json').write_bytes(json_bytes(index))
            print(f'{len(previews)} mechanism inputs exported to {args.output.resolve()}; '
                  f'{len(mechanism_inputs.MECHANISMS)-len(mechanism_inputs.implemented())} '
                  'mechanisms still unimplemented. No registration or model calls.')
            return
        if args.scenario == 'all':
            raise ValueError('--scenario all requires --mechanism')
        if args.threat_cell:
            if args.world_config or args.binding_preset or args.combined_bindings:
                raise ValueError('--threat-cell supplies the world and binding; do not combine overrides')
            cells = list(threat_grid.CELLS) if args.threat_cell == 'all' else [args.threat_cell]
            # Materialize before writing so an invalid cell cannot leave a partial matrix.
            previews = {cell: build_preview(args.scenario, threat_grid.CELLS[cell]['preset'],
                        harness=args.harness, cell=cell) for cell in cells}
            if args.threat_cell == 'all':
                args.output.mkdir(parents=True, exist_ok=False)
                for cell, (manifest, subjects) in previews.items():
                    write_preview(args.output/cell, manifest, subjects)
                index = {'kind': 'offline_threat_grid_inputs', 'domain': args.scenario,
                         'cells': {cell: {'manifest': cell+'/manifest.json',
                                         'input_sha256': scenario.digest(subjects),
                                         'criterion': threat_grid.CELLS[cell]['criterion']}
                                   for cell, (_, subjects) in previews.items()},
                         'execution_paths': 'not_run', 'model_behavior': 'not_tested'}
                (args.output/'manifest.json').write_bytes(json_bytes(index))
            else:
                write_preview(args.output, *previews[args.threat_cell])
            print(f'{len(cells)} grid input(s) exported to {args.output.resolve()} (no registration or model calls).')
            return
        overrides = (json.loads(args.world_config.read_text(encoding='utf-8'))
                     if args.world_config else None)
        manifest, subjects = build_preview(args.scenario, args.binding_preset or 'control', overrides,
            combined=args.combined_bindings, harness=args.harness)
        write_preview(args.output, manifest, subjects)
    except (OSError, ValueError, ValidationError) as error:
        parser.error(str(error))
    print(f'Business inputs exported to {args.output.resolve()} (no registration or model calls).')


if __name__ == '__main__':
    main()
