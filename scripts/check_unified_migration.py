#!/usr/bin/env python3
"""Replay preserved positive evidence against the common input implementation.

Reads extracted private Release archives; never changes them or calls a model.
Native-record equivalence checks the evidence interface, not a new business run.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'experiments/swarmharm-v1'), str(REPO/'experiments/runtime')]
from phase2 import delivery_handoff, delivery_record_review, unified_delivery as scenario
from phase2.trace_review import captured

CASES = {
    'r8': ('2026-11-05-unified-report-inputs-records-sol56-r8',
           'records', 'unified-report-uploads.json'),
    'r17': ('2026-11-05-unified-engineering-confirmation-sol56-r17',
            'resource', 'unified-shared-headroom.json'),
    'r26': ('2026-11-05-unified-readiness-wording-sol56-r26',
            'control', 'unified-delayed-account-view.json'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(root, path):
    return json.loads((root/path).read_text())


def replay_business(archive, case):
    name, preset, config = CASES[case]
    root = archive/name
    plan = deepcopy(read(root, 'registration.json')['phase2']['assignments'])
    events = read(root, 'natural/world.json')['events']
    world = scenario.world_config.normalize(
        read(REPO/'experiments/swarmharm-v1/configs', config), preset=preset)
    require(world == scenario.world_for(plan), case+': normalized settings differ')
    for assignment in plan.values():
        assignment.update(world_config=world, delivery_config=scenario.world_config.components(world)[0])
    prior = scenario.inspect_final_files(plan, root/'natural/operator/delivery-files')
    with TemporaryDirectory(prefix='swarmharm-input-migration-') as temporary:
        output = Path(temporary)
        replay = scenario.replay_sequences(events, plan, list(plan), output/'joint', root/'natural')
        require(all(row['original_status'] == row['replayed_status']
                    for row in replay['actions'] if row['business_mutation']),
                case+': action results differ')
        require(all(replay['effects'][key] == value for key, value in prior.items()),
                case+': final effects differ')
        result = {'case': name, 'world_config': config, 'preset': preset,
                  'normalized_world_equal': True, 'business_action_statuses_equal': True,
                  'prior_terminal_effects_preserved': True, 'effects': prior}
        if preset == 'resource':
            composition = scenario.composition_replay(events, plan, output/'composition', root/'natural')
            require(composition['composition_passed'], 'Full-sequence composition no longer holds')
            result['full_sequence_composition_preserved'] = True
        if case == 'r26':
            without = [event for event in events if event['operation'] not in
                       ('post_delivery_message', 'read_delivery_discussion')]
            other = scenario.replay_sequences(without, plan, list(plan), output/'no-discussion', root/'natural')
            business = lambda rows: [row for row in rows['actions'] if row['business_mutation']]
            require(business(replay) == business(other) and replay['effects'] == other['effects'],
                    'Discussion unexpectedly became a business prerequisite')
            result['discussion_not_business_prerequisite'] = True
        return result


def native_interface(archive):
    root = archive/'2026-11-04-record-append-sol56-r261'
    registration = read(root, 'registration.json')
    plan = registration['phase2']['assignments']
    original = read(root, 'natural/world.json')['events']
    continuation = read(root, 'natural/continuation.json')['state']
    events = deepcopy(original)
    comparisons = []
    # Alias old evidence field/tool names for the current independent reader.
    # This does not replay or translate the original business task.
    for event in events:
        if 'record_capture' in event:
            actor = event['actor']
            records = captured(root/'natural', event['record_capture'], actor)
            old = event['quality']['sections']['work_record_alignment']['matched_entries']
            current = delivery_handoff.check(plan[actor], records=records)['observed_entries']
            require(old == current, f"r261: native input differs at event {event['id']}")
            comparisons.append({'event': event['id'], 'actor': actor,
                                'prior_reference_entries': old, 'unified_reference_entries': current})
            event['activity_input'] = event['record_capture']
        event['operation'] = {'check_briefing': 'check_delivery', 'publish_briefing': 'release_delivery',
                              'withdraw_briefing': 'withdraw_delivery'}.get(event['operation'], event['operation'])
    native = delivery_record_review.reconstruct(root/'natural', plan, events,
        continuation['final_records'], continuation['deliveries'])
    prior = read(root, 'semantic-review.json')['independent_effect']
    counts = {row['actor']: row['retained_changes'] for row in native['owners']}
    require(native['verified'] and counts == prior['owner_attribution'],
            'r261: independent retained-record accounting differs')
    require(native['published_retained_changes'] == prior['final_record_changes'],
            'r261: retained publication effect differs')
    return {'case': 'r261', 'scope': 'Evidence-interface equivalence only; task and behavior are not replayed.',
            'all_captured_reference_counts_equal': True, 'capture_comparisons': comparisons,
            'independent_record_accounting_equal': True, 'retained_changes_by_actor': counts,
            'published_retained_changes': native['published_retained_changes'],
            'current_native_task_behavior_established': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, required=True,
                        help='Directory containing extracted case folders from private Releases')
    parser.add_argument('--output', type=Path, help='Optional new JSON report; existing files are not overwritten')
    args = parser.parse_args()
    report = {'scope': 'Preserved evidence on current source; no new model behavior.',
              'source_revision': scenario.REVISION,
              'cases': [replay_business(args.archive_root, case) for case in CASES],
              'native_interface': native_interface(args.archive_root)}
    encoded = json.dumps(report, indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(encoded)
    print(encoded)


if __name__ == '__main__':
    main()
