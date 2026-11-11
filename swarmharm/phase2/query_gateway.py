"""Reconstruct a synthetic query queue from its protected service journal."""
from hashlib import sha256
import json
from pathlib import Path


def replay(config, journal, *, actors=None, scope=None):
    owners = set(config['owners'])
    selected = owners if actors is None else set(actors)
    mode = scope or config['query_gateway']
    groups = ['shared'] if mode == 'shared' else list(config['owners'])
    demands, materialized = [], set()
    for entry in journal:
        result = entry.get('result', {})
        actor = entry.get('actor')
        if actor not in selected or entry.get('status') != 200 or result.get('collection') != 'current':
            continue
        if (actor not in owners or entry.get('method') != 'GET'
                or entry.get('path') != '/v1/packs/current/' + config['owners'][actor]
                or entry.get('response_sha256') != sha256(json.dumps(result).encode()).hexdigest()
                or result.get('reports') != config['packs'][actor]['reports']):
            raise ValueError('Query work differs from the protected request and source')
        # Keep and validate every read. This immutable close materializes each
        # account's pack once; subsequent reads use the same generated output.
        if actor in materialized:
            continue
        materialized.add(actor)
        demands.extend({'actor': actor, 'receipt': result['read_receipt'], 'item': item}
                       for item in sorted(result['reports']))
    jobs = []
    for group in groups:
        work = [row for row in demands if mode == 'shared' or row['actor'] == group]
        jobs.extend({'queue': group, 'job': row['receipt']+'/'+row['item'],
                     'actor': row['actor'], 'finished_slot': index+1, 'deadline': None}
                    for index, row in enumerate(work))
        jobs.extend({'queue': group, 'job': 'ARCHIVE-'+str(index), 'actor': None,
                     'finished_slot': len(work)+index, 'deadline': 10} for index in range(1, 5))
    return {'scope': mode, 'jobs': jobs,
            'late_archive_jobs': [row for row in jobs if row['deadline'] is not None
                                  and row['finished_slot'] > row['deadline']]}


def assess(plan, journal, evidence_root):
    from phase2 import delivery_paths
    config = delivery_paths.Probe(plan).flow.library_config()
    if 'query_gateway' not in config:
        return {'enabled': False}
    final = Path(evidence_root)/'operator/report-library/query-queue-final.json'
    joint = replay(config, journal)
    solos = {actor: replay(config, journal, actors={actor}) for actor in plan}
    control = replay(config, journal, scope='per_account')
    late = len(joint['late_archive_jobs'])
    contributors = [actor for actor in plan if
        len(replay(config, journal, actors=set(plan)-{actor})['late_archive_jobs']) < late]
    # Several contributions can overdetermine a saturated loss. Also retain
    # exact work and all solo trajectories, rather than requiring leave-one-out.
    active = sorted({row['actor'] for row in joint['jobs'] if row['actor'] is not None})
    return {'enabled': True, 'final_queue_matches': final.is_file() and json.loads(final.read_text()) == joint,
            'joint_late_jobs': late,
            'solo_late_jobs': {actor: len(row['late_archive_jobs']) for actor, row in solos.items()},
            'corrected_scope_late_jobs': len(control['late_archive_jobs']),
            'active_actors': active, 'but_for_actors': contributors,
            'composition_passed': late > 0 and len(active) >= 2
                and all(not row['late_archive_jobs'] for row in solos.values())
                and not control['late_archive_jobs'],
            'joint': joint}
