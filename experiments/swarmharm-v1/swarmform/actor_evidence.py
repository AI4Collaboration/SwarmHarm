"""Strict per-actor exports, coverage and sealing for closed SwarmForm rollouts."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


def export_closed_actors(root, registration):
    """Attempt every actor independently, preserving failures and strict validation.

    A bad native trajectory must not prevent healthy peers from being exported.
    The existing export_actor checks remain authoritative; failed actors never
    receive continuity credit or a fabricated replacement trajectory.
    """
    from export_atif import export_actor
    root = Path(root)
    if not (root / 'completion.json').is_file():
        raise ValueError('Wait for terminal collection')
    dest = root / 'atif-validation.json'
    if dest.exists():
        raise FileExistsError('Do not replace an export')
    trajectories, failures = [], []
    for phase, plan in registration['plan'].items():
        for actor in plan:
            try:
                if not (root / phase / actor / 'history.json').is_file():
                    raise FileNotFoundError('Missing actor history')
                trajectories.append(export_actor(root, phase, actor))
            except Exception as error:
                failures.append({'phase': phase, 'actor': actor,
                                 'type': type(error).__name__, 'message': str(error)})
    report = {'harbor_version': '0.24.0', 'schema': 'ATIF-v1.8',
              'trajectories': trajectories, 'failed_trajectories': failures,
              'all_registered_actors_exported': bool(trajectories) and not failures}
    with dest.open('x') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def completeness(root, registration, trajectories=None):
    """Inventory native/ATIF actors without changing or re-exporting evidence.

    A validated trajectory can describe one actor in a partial rollout. Its
    continuity flag therefore cannot stand in for the registered actor set.
    """
    root = Path(root)
    registered = set(registration.get('plan', {}).get('natural', {}))
    natural = root / 'natural'
    native = {folder.name for folder in natural.iterdir()
              if folder.is_dir() and any((folder / 'codex/native').glob('*.json'))} if natural.is_dir() else set()
    if trajectories is None:
        validation = root / 'atif-validation.json'
        trajectories = json.loads(validation.read_text()).get('trajectories', []) if validation.is_file() else []
    rows = [row for row in trajectories if row.get('phase') == 'natural']
    counts = Counter(row['actor'] for row in rows)
    atif = set(counts)
    verified = {row['actor'] for row in rows if row.get('native_continuity_passed') is True}
    duplicates = sorted(actor for actor, count in counts.items() if count != 1)
    other_phases = [{'phase': row.get('phase'), 'actor': row.get('actor')}
                    for row in trajectories if row.get('phase') != 'natural']
    allowed = (4, 8, 16, 32) if registration.get('study_mode') == 'swarmform-structure' else (3,)
    registration_complete = registration.get('population') in allowed and len(registered) == registration.get('population')
    native_complete = native == registered
    atif_complete = atif == registered and not duplicates and not other_phases
    continuity_complete = native_complete and atif_complete and verified == registered
    complete = registration_complete and native_complete and continuity_complete
    return {
        'registered_actors': sorted(registered),
        'native_actors': sorted(native),
        'atif_actors': sorted(atif),
        'continuity_verified_actors': sorted(verified),
        'registration_actor_set_complete': registration_complete,
        'native_actor_set_complete': native_complete,
        'atif_actor_set_complete': atif_complete,
        'native_continuity_complete': continuity_complete,
        'missing_actors': {'native': sorted(registered - native), 'atif': sorted(registered - atif),
                           'verified_continuity': sorted(registered - verified)},
        'unexpected_actors': {'native': sorted(native - registered), 'atif': sorted(atif - registered)},
        'duplicate_atif_actors': duplicates,
        'unexpected_atif_phases': other_phases,
        'actor_evidence_complete': complete,
        'actor_coverage_status': 'complete' if complete else 'partial',
        'scope': 'Actor coverage and recorded native/ATIF continuity only; runtime disposition, business completion and semantic review remain separate.',
    }


def require_unfinalized(root):
    """Finalization is one-shot; a later review must use a separate artifact."""
    root = Path(root)
    for name in ('evidence-manifest.json', 'collection-summary.json', 'atif-validation.json'):
        if (root / name).exists():
            raise FileExistsError('Preserve existing finalization: ' + name)


def finalize_actor_evidence(root, registration):
    """Run export and coverage independently, even for a partially failed cohort."""
    from swarmform.collection import save
    root = Path(root)
    failures, coverage = [], None
    try:
        exported = export_closed_actors(root, registration)
        if exported['failed_trajectories']:
            failures.append('atif')
            save(root / 'atif-failure.json', {'failed_trajectories': exported['failed_trajectories']})
    except Exception as error:
        failures.append('atif')
        save(root / 'atif-failure.json', {'type': type(error).__name__, 'message': str(error)})
    try:
        coverage = completeness(root, registration)
        save(root / 'actor-evidence.json', coverage)
        if not coverage['actor_evidence_complete']:
            failures.append('actor_evidence')
    except Exception as error:
        failures.append('actor_evidence')
        save(root / 'actor-evidence-failure.json', {'type': type(error).__name__, 'message': str(error)})
    return coverage, failures


def seal_collection(root, summary):
    """Write the terminal summary before hashing all immutable evidence files."""
    from swarmform.collection import save, utc
    root = Path(root)
    for name in ('collection-summary.json', 'evidence-manifest.json'):
        if (root / name).exists():
            raise FileExistsError('Preserve existing finalization: ' + name)
    save(root / 'collection-summary.json', summary)
    excluded = ['evidence-manifest.json', 'controller.log', '.collector.lock']
    files = {}
    for path in sorted(root.rglob('*')):
        relative = str(path.relative_to(root))
        if path.is_file() and not path.is_symlink() and relative not in excluded:
            with path.open('rb') as stream:
                digest = sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            files[relative] = digest.hexdigest()
    save(root / 'evidence-manifest.json', {'at': utc(), 'files': files, 'excluded': excluded})
    return summary
