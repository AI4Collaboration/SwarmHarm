import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    release = json.loads((args.directory / 'release.json').read_text())
    objective = (Path(__file__).parent / 'objective.txt').read_text().strip()
    observations = sorted((args.directory / 'observations').glob('snapshot-*.json'))
    snapshot = next(json.loads(path.read_text()) for path in reversed(observations)
                    if 'hosts' in json.loads(path.read_text()))
    hosts = {host['instance_id']: host for host in snapshot['hosts']}
    assert set(hosts) == {host['id'] for host in binding['hosts']}
    starts = []
    goals = []
    subjects = []
    for host_id, host in hosts.items():
        assert host['markers'] == [host_id]
        persisted = host['persisted_goals']
        assert len(persisted) == 1 and persisted[0]['objective'] == objective
        assert host['goal-submitted']['objective'] == objective
        start = host['codex-process-start']['create_time'] + host['boot-clock-correction']['psutil_epoch_correction_seconds']
        starts.append(start)
        accepted = persisted[0]['created_at_ms'] / 1000
        goals.append(accepted)
        subjects.append({'instance_id': host_id, 'session_id': persisted[0]['thread_id'],
                         'process_start': start, 'goal_accepted': accepted})
    assert min(starts) >= release['T_start'] - 0.1
    assert len({subject['session_id'] for subject in subjects}) == len(subjects)
    result = {'subjects': len(subjects), 'T_start': release['T_start'],
              'process_start_skew_seconds': max(starts) - min(starts),
              'goal_acceptance_skew_seconds': max(goals) - min(goals),
              'objective_sha256': hashlib.sha256(objective.encode()).hexdigest(),
              'snapshot_time': snapshot['time'], 'native_goal_launches': subjects}
    (args.directory / 'launch-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({name: value for name, value in result.items() if name != 'native_goal_launches'}))


if __name__ == '__main__':
    main()
