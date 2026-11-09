"""Read-only actor coverage for a closed three-agent SwarmForm rollout."""

from collections import Counter
import json
from pathlib import Path


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
