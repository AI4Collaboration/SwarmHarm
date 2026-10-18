import argparse
import concurrent.futures
import json
from pathlib import Path

from cloud import ROOT, save, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    release = json.loads((args.directory / 'release.json').read_text())
    objective = (ROOT / 'objective.txt').read_text().strip()
    def inspect(host):
        response = ssh(args.directory, host['public_ip'], 'sudo python3 -',
                       (ROOT / 'launch_state.py').read_bytes(), check=False)
        save(args.directory, f'{host["id"]}-launch-command.json',
             {'instance_id': host['id'], 'returncode': response.returncode,
              'stdout': response.stdout.decode(), 'stderr': response.stderr.decode()})
        response.check_returncode()
        result = json.loads(response.stdout)
        assert result['markers'] == [host['id']]
        assert result['process-start']['instance_id'] == host['id']
        assert result['goal-submitted']['objective'] == objective
        goals = result['native-goals']['goals']
        assert len(goals) == 1 and goals[0]['objective'] == objective
        save(args.directory, f'{host["id"]}-launch-verification.json', result)
        return {'instance_id': host['id'], 'thread_id': goals[0]['thread_id'],
                'process_start': result['codex-process-start']['create_time'] +
                result['boot-clock-correction']['psutil_epoch_correction_seconds'],
                'goal_accepted': goals[0]['created_at_ms'] / 1000}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(inspect, binding['hosts']))
    report = {'subjects': len(rows), 'T_start': release['T_start'], 'rows': rows,
              'process_start_skew_seconds': max(row['process_start'] for row in rows) - min(row['process_start'] for row in rows),
              'goal_acceptance_skew_seconds': max(row['goal_accepted'] for row in rows) - min(row['goal_accepted'] for row in rows)}
    save(args.directory, 'launch-verification.json', report)
    print(json.dumps({name: value for name, value in report.items() if name != 'rows'}))


if __name__ == '__main__':
    main()
