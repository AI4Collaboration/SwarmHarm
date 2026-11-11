#!/usr/bin/env python3
"""Validate the balanced headline matrix without launching models."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / 'swarmharm'),
                str(REPO / 'shared')]

from phase2 import balanced_study, delivery_paths, unified_delivery as scenario


ACTORS = ('job-northline', 'job-aster', 'job-meridian', 'job-harbor')


def plan_for(domain, preset):
    world = balanced_study.expected_world(preset)
    config, _ = scenario.world_config.components(world)
    plan = scenario.plan_for(ACTORS, domain=domain)
    for assignment in plan.values():
        assignment.update(
            binding_preset=preset,
            world_config=deepcopy(world),
            delivery_config=deepcopy(config),
            continuous_workflow=True,
            work_entries_only=True,
            native_record_harness='codex',
        )
    return plan


def input_matrix():
    cells = []
    input_fixed = set()
    for domain in balanced_study.DOMAINS:
        for preset, claim in balanced_study.PRESET_CLAIMS.items():
            plan = plan_for(domain, preset)
            manifest = balanced_study.input_manifest(plan)
            paths = delivery_paths.audit(plan)
            delivery_paths.require_challenge(paths, preset, claim)
            input_fixed.add(manifest['fixed_factors_sha256'])
            cells.append({
                'domain': domain,
                'domain_role': manifest['registered_variables']['domain_role'],
                'preset': preset,
                'target_claim': claim,
                'changed_bindings': manifest['registered_variables']['changed_bindings'],
                'subject_sha256': manifest['subject_input_contract']['subject_sha256'],
                'input_fixed_factors_sha256': manifest['fixed_factors_sha256'],
                'path_validation': {
                    'condition': paths['condition'],
                    'normal_completion_available': paths['normal_completion_available'],
                    'each_actor_has_tested_alternative': paths['each_actor_has_tested_alternative'],
                    'world_sha256': paths['world_sha256'],
                },
            })
    return cells, input_fixed


def registration_matrix(paths):
    manifests = []
    for path in paths:
        source = path / 'registration.json' if path.is_dir() else path
        manifests.append(balanced_study.registration_manifest(
            json.loads(source.read_text(encoding='utf-8'))))
    return balanced_study.compare_manifests(manifests, require_complete=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', type=Path, action='append', default=[],
                        help='Optional prepared registration file or directory; repeat for a comparison set.')
    parser.add_argument('--output', type=Path,
                        help='Write the JSON report to this path; stdout otherwise.')
    args = parser.parse_args(argv)
    cells, fixed = input_matrix()
    report = {
        'kind': 'balanced_headline_input_readiness',
        'revision': balanced_study.REVISION,
        'design': balanced_study.NAME,
        'primary_domain': balanced_study.PRIMARY_DOMAIN,
        'replication_domain': balanced_study.REPLICATION_DOMAIN,
        'four_domain_stress_block': list(balanced_study.STRESS_DOMAINS),
        'presets': balanced_study.PRESET_CLAIMS,
        'model_blocks': list(balanced_study.MODELS),
        'world_config': str(balanced_study.CONFIG_PATH.relative_to(REPO)),
        'world_config_sha256': scenario.digest(balanced_study.world_override()),
        'allowed_variable_factors': [
            'model_identity', 'domain_payload', 'selected_binding', 'target_claim'
        ],
        'input_fixed_factor_hashes': sorted(fixed),
        'cells': cells,
        'prepared_registration_alignment': (
            registration_matrix(args.registration) if args.registration else None),
        'model_calls': 0,
        'passed': len(fixed) == 1 and all(
            row['path_validation']['condition'] == 'blocked_challenge'
            and row['path_validation']['each_actor_has_tested_alternative']
            for row in cells),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    else:
        print(rendered, end='')
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
