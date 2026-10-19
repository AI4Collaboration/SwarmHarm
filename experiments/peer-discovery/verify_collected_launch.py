import argparse
from collections import Counter
import json
from pathlib import Path

from cloud import save
from subject_state import subject_state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    release = json.loads((args.directory / 'release.json').read_text())
    rows = []
    for host in binding['hosts']:
        root = args.directory / host['id'] / 'var/lib/peer-operator'
        state = subject_state(args.directory, host['id'])
        collection = json.loads((root / 'collection-receipt.json').read_text())
        assert collection['launch_markers'] == [host['id']]
        process = json.loads((root / 'codex-process-start.json').read_text())
        correction = json.loads((root / 'boot-clock-correction.json').read_text())
        assert process['instance_id'] == host['id']
        goal = state['goal']
        rows.append({'instance_id': host['id'], 'state': state['state'],
                     'startup_diagnostic': state.get('startup_diagnostic'),
                     'thread_id': goal['thread_id'] if goal else None,
                     'process_start': process['create_time'] + correction['psutil_epoch_correction_seconds'],
                     'goal_accepted': goal['created_at_ms'] / 1000 if goal else None})
    accepted = [row['goal_accepted'] for row in rows if row['goal_accepted'] is not None]
    result = {'subjects': len(rows), 'T_start': release['T_start'], 'rows': rows,
              'states': dict(Counter(row['state'] for row in rows)),
              'accepted_goals': len(accepted),
              'process_start_skew_seconds': max(row['process_start'] for row in rows) - min(row['process_start'] for row in rows),
              'goal_acceptance_skew_seconds': max(accepted) - min(accepted) if accepted else None,
              'basis': 'Collected process receipts, native goals, session metadata and PTY startup diagnostics.'}
    save(args.directory, 'collected-launch-verification.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'rows'}))


if __name__ == '__main__':
    main()
