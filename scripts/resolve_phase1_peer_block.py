"""Resolve the next arm of the preregistered Data Analysis peer block from reviewed evidence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def resolve(repo, profile):
    ledger = load(repo / 'docs/research/phase1-readiness.json')
    peer = next(p for p in ledger['pressure_conditions'] if p['id'] == 'peer_preservation')
    block = peer['next_development_block']
    plan_path = (repo / block['plan']).resolve()
    require(digest(plan_path) == block['sha256'], 'Changed prospective peer plan')
    plan = load(plan_path)
    require(plan['scenario'] == block['scenario'] == 'data-analysis' and plan['channel'] == 'cache_value'
            and plan['order'] == ['peer_preservation', 'peer_ordinary'] and profile in plan['order'],
            'Unexpected block or arm')
    require(plan['source_commit'] == ledger['current_source_commit'] and
            digest(repo / 'experiments/swarmharm-v1/scenarios/data_analysis.py') == plan['source_domain_sha256'],
            'The prospective block requires its registered source')
    index_spec = ledger['publication_analysis']
    index_path = repo / index_spec['registration_index']
    require(digest(index_path) == index_spec['registration_index_sha256'], 'Stale registration index')
    rows = load(index_path)['registrations']
    require(len(rows) == index_spec['reviewed_registrations'] and all(r['review_status'] == 'complete' for r in rows),
            'An indexed rollout still needs review')
    current_source = next(r['registered_code_sha256'] for r in rows if r['rollout'] == 8)
    rows_on_source = [r for r in rows if r['registered_code_sha256'] == current_source]
    prereqs = {(scenario, channel, scope)
               for scenario, channels in [('engineering-capacity', ('E1', 'E2.1', 'E2.2')), ('data-analysis', ('E1',))]
               for channel in channels for scope in ('vulnerable', 'repaired')}
    ordinary = {(r['scenario'], r['channel'], r['isolation']): r for r in rows_on_source if r['resource_profile'] == 'ordinary_work'}
    missing = sorted(prereqs - ordinary.keys())
    require(not missing, 'Pending current-source ordinary reviews: ' + ', '.join('/'.join(k) for k in missing))
    previous = [r for r in rows_on_source if r['scenario'] == plan['scenario'] and r['channel'] == 'E1'
                and r['isolation'] == 'vulnerable' and r['resource_profile'] in plan['order']]
    require([r['resource_profile'] for r in previous] == plan['order'][:plan['order'].index(profile)],
            'This arm already exists or its declared predecessor is missing')
    for r in [ordinary[k] for k in sorted(prereqs)] + previous:
        source = plan_path.parent / r['evidence_directory']
        seal = load(source / 'phase1-review-evidence-index.json')
        require(seal['sealed_source_matches'] == plan['source_commit'] and seal['review_complete']
                and seal['registration_commit'] == r['registration_commit'] and r['native_continuity_verified']
                and digest(source / 'registration.json') == r['registration_sha256']
                and digest(source / 'phase1-review-evidence-index.json') == r['evidence']['phase1-review-evidence-index.json'],
                'Incomplete or mismatched source review in ' + r['evidence_directory'])
        if r['resource_profile'] in plan['order']:
            require(digest(source / 'phase1-peer-validation-plan.json') == block['sha256'], 'Prior arm belongs to another plan')
    ref = previous[-1] if previous else ordinary[('data-analysis', 'E1', 'vulnerable')]
    return {'scenario': plan['scenario'], 'domain':'Data Analysis', 'arm':profile, 'serial':rows[-1]['rollout'] + 1,
            'predecessor':rows[-1]['evidence_directory'], 'reference':ref['evidence_directory'], 'plan':str(plan_path),
            'plan_sha256':block['sha256'], 'prerequisite_registrations':[ordinary[k]['registration_sha256'] for k in sorted(prereqs)]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=['peer_preservation', 'peer_ordinary'])
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        print(json.dumps(resolve(args.repo, args.profile), indent=2))
    except ValueError as error:
        parser.exit(2, str(error) + '\n')
