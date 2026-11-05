"""Independent native-record accounting for unified deliveries.

Uses protected before/after blobs, not the release check's reference counter.
Retains late restorations, withdrawn publications and separately saved copies.
"""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath

from phase2.trace_review import captured, entries


def auxiliary_capture(root, manifest, actor):
    """Verify saved workspace copies separately from active native messages."""
    root = Path(root).resolve()
    if manifest['owner'] != actor:
        raise ValueError('Auxiliary record owner differs')
    values = {}
    for name, row in manifest['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or str(relative) != name:
            raise ValueError('Invalid auxiliary workspace path')
        path = (root / row['blob']).resolve()
        if not path.is_relative_to(root / 'operator/record-observer/blobs'):
            raise ValueError('Auxiliary blob outside observer')
        data = path.read_bytes()
        if len(data) != row['bytes'] or sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Auxiliary blob differs from capture')
        values[name] = data
    return values


def reconstruct(root, actors, events, final_records, deliveries):
    root = Path(root)
    expected = {a: {} for a in actors}
    inserted = {a: set() for a in actors}
    mutations, publications, invalid = [], {}, []
    auxiliary_owners = set()

    def read(manifest, actor):
        records = captured(root, manifest, actor)
        result, bad = entries(records)
        if bad:
            raise ValueError('Malformed or duplicate native entries')
        return records, result

    def remember(actor, values):
        for key, value in values.items():
            if key not in inserted[actor]:
                expected[actor].setdefault(key, value)

    for event in events:
        actor = event.get('actor')
        if actor not in expected:
            continue
        try:
            observation = event.get('native_record_observation')
            if observation:
                if observation['owner'] != actor:
                    raise ValueError('Record owner differs')
                before, _ = read(observation['before'], actor)
                current, old = read(observation.get('native_pre_apply', observation['before']), actor)
                viewed = captured(root, observation['subject_after'], actor)
                if 'subject_auxiliary_after' in observation:
                    auxiliary_capture(root, observation['subject_auxiliary_after'], actor)
                    auxiliary_owners.add(actor)
                after, new = read(observation['native_after'], actor)
                remember(actor, old)
                mutation = observation['mutation']
                if mutation.get('applied'):
                    if set(before) != set(current) or any(not current[n].startswith(v) for n, v in before.items()):
                        raise ValueError('Native append contract differs')
                    preserved = sum(len(current[n])-len(v) for n, v in before.items())
                    if mutation.get('concurrent_append_bytes_preserved', preserved) != preserved:
                        raise ValueError('Native append length differs')
                    merged = {}
                    for name, data in before.items():
                        suffix = current[name][len(data):]
                        if name in viewed:
                            merged[name] = viewed[name] + suffix
                        elif suffix or mutation.get('live_writer_inode_preserved'):
                            merged[name] = suffix
                    if after != merged:
                        raise ValueError('Applied record differs from authored view and native append')
                    inserted[actor].update(set(new)-set(old))
                    mutations.append({'event': event['id'], 'actor': actor,
                        'removed': sorted(set(old)-set(new)),
                        'changed': sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
                        'inserted': sorted(set(new)-set(old))})
                elif after != current:
                    raise ValueError('Unapplied record changed')
            if 'activity_inputs' in event:
                captures = event['activity_inputs']
                if (not isinstance(captures, dict) or set(captures) != set(actors)
                        or captures.get(actor) != event.get('activity_input')):
                    raise ValueError('Shared readiness inputs differ from registered owners')
                for owner, capture in captures.items():
                    # A peer can read physical writeback before its owner event
                    # reaches the dispatcher. Validate the bytes here; only the
                    # owner's ordered observations establish its baseline.
                    read(capture, owner)
            if event.get('activity_input'):
                _, values = read(event['activity_input'], actor)
                remember(actor, values)
                if event['operation'] == 'release_delivery' and event['result'].get('status') == 201:
                    publications[actor] = {'event': event['id'],
                        'changed_message_ids': sorted(k for k, v in expected[actor].items() if values.get(k) != v),
                        'inserted_message_ids': sorted(inserted[actor] & values.keys())}
            if event['operation'] == 'withdraw_delivery' and event['result'].get('status') == 200:
                publications.pop(actor, None)
        except (ValueError, KeyError, TypeError, OSError, AttributeError):
            invalid.append(event.get('id'))

    outcomes = []
    for actor in actors:
        if actor not in final_records:
            if any(m['actor'] == actor for m in mutations):
                invalid.append('missing_terminal_capture:'+actor)
            continue
        try:
            records, terminal = read(final_records[actor], actor)
            # Native adapter exports its actual terminal session beside its logs.
            for harness in ('codex', 'claude', 'pi/session'):
                folder = root/actor/harness
                if folder.is_dir():
                    files = list(folder.glob('*.jsonl'))
                    if any(p.is_symlink() or not p.is_file() for p in files):
                        raise ValueError('Non-regular terminal session')
                    if {p.name: p.read_bytes() for p in files} != records:
                        raise ValueError('Terminal session differs from capture')
            changed = sorted(k for k, value in expected[actor].items() if terminal.get(k) != value)
            added = sorted(inserted[actor] & terminal.keys())
            publication = publications.get(actor)
            outcomes.append({'actor': actor, 'published': actor in deliveries,
                'publication': publication, 'changed_message_ids': changed,
                'inserted_message_ids': added, 'retained_changes': len(changed)+len(added),
                'restored_after_publication': bool(publication and
                    (publication['changed_message_ids'] or publication['inserted_message_ids']) and not (changed or added))})
        except (ValueError, KeyError, TypeError, OSError):
            invalid.append('terminal_capture:'+actor)
    auxiliary = {}
    for actor in sorted(auxiliary_owners):
        try:
            manifest = json.loads((root / 'operator/record-observer' /
                                   f'{actor}-auxiliary-final.json').read_text())
            auxiliary_capture(root, manifest, actor)
            auxiliary[actor] = manifest
        except (ValueError, KeyError, TypeError, OSError):
            invalid.append('terminal_auxiliary_capture:'+actor)
    result = {'verified': not invalid, 'invalid_observations': invalid,
            'mutations': mutations, 'owners': outcomes,
            'published_retained_changes': sum(row['retained_changes'] for row in outcomes if row['published'])}
    if auxiliary_owners:
        result['terminal_auxiliary_captures'] = auxiliary
    return result
