import argparse
import concurrent.futures
import json
from pathlib import Path

from cloud import ROOT, ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())

    def observe(host):
        result = ssh(args.directory, host['public_ip'], 'sudo python3 -', (ROOT / 'inspect_goal.py').read_bytes(), check=False)
        if result.returncode:
            return {'instance_id': host['id'], 'observation': 'initializing'}
        body = json.loads(result.stdout)
        goals = [row for table in body if table['schema']['name'] == 'thread_goals' for row in table['rows']]
        if not goals:
            return {'instance_id': host['id'], 'observation': 'initializing'}
        assert len(goals) == 1
        goal = goals[0]
        return {'instance_id': host['id'], 'status': goal['status'], 'tokens_used': goal['tokens_used'],
            'time_used_seconds': goal['time_used_seconds'], 'thread_id': goal['thread_id'],
            'created_at_ms': goal['created_at_ms'], 'updated_at_ms': goal['updated_at_ms'],
            'objective': goal['objective']}

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        print(json.dumps(list(pool.map(observe, binding['hosts'])), indent=2))


if __name__ == '__main__':
    main()
