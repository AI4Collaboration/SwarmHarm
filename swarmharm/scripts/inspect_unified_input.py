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
from phase2 import office_history, unified_delivery as scenario, world_config

ACTORS = ('job-northline', 'job-aster', 'job-meridian', 'job-harbor')


def build_preview(domain, preset, overrides=None, *, combined=False, harness='codex'):
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
    parser.add_argument('--scenario', choices=scenario.delivery_data.DOMAINS,
                        default='engineering-capacity')
    parser.add_argument('--binding-preset', choices=scenario.PRESETS, default='control')
    parser.add_argument('--world-config', type=Path)
    parser.add_argument('--combined-bindings', action='store_true')
    parser.add_argument('--harness', choices=('codex', 'claude-code'), default='codex',
                        help='Select initial activity-file layout only; does not launch a harness')
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory for the operator preview, not a registration')
    args = parser.parse_args(argv)
    try:
        overrides = (json.loads(args.world_config.read_text(encoding='utf-8'))
                     if args.world_config else None)
        manifest, subjects = build_preview(args.scenario, args.binding_preset, overrides,
            combined=args.combined_bindings, harness=args.harness)
        write_preview(args.output, manifest, subjects)
    except (OSError, ValueError, ValidationError) as error:
        parser.error(str(error))
    print(f'Business inputs exported to {args.output.resolve()} (no registration or model calls).')


if __name__ == '__main__':
    main()
