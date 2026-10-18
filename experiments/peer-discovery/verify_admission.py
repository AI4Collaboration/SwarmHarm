import argparse
import hashlib
import json
from pathlib import Path

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory
    binding = json.loads((directory / 'binding.json').read_text())
    assert len(binding['hosts']) == 1
    host = binding['hosts'][0]
    root = directory / host['id'] / 'var/lib/peer-operator'
    goals = json.loads((root / 'native-goals.json').read_text())['goals']
    assert len(goals) == 1 and goals[0]['status'] == 'complete'
    assert goals[0]['objective'] == Path(__file__).with_name('preflight-objective.txt').read_text().strip()
    stopped = json.loads((root / 'process-stop.json').read_text())
    assert stopped['goal_complete'] and stopped['submitted']
    assert json.loads((root / 'frozen-output.json').read_bytes()) == []
    shell = (directory / host['id'] / 'home/agent/shell-admission.txt').read_text()
    assert 'uid=1001(agent)' in shell and 'UTC' in shell
    gateway = json.loads((directory / 'gateway-0.json').read_text())
    successful = [edge['node'] for edge in gateway['requests']['edges'] if edge['node']['status'] == 'completed']
    assert successful
    assert all(request['modelID'] == 'gpt-6-luna' and request['reasoningEffort'] == 'xhigh' for request in successful)
    for request in successful:
        assert any(edge['node']['status'] == 'completed' and edge['node']['upstreamModelID'] == 'gpt-6-luna'
                   for edge in request['executions']['edges'])
    recordings = json.loads((directory / 'recording-receipts.json').read_text())
    assert recordings['request_count'] == len(gateway['requests']['edges'])
    for item in recordings['objects']:
        raw = (directory / 'stored-payloads' / item['object_key']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['sha256']
    cleanup = json.loads((directory / 'cleanup.json').read_text())
    assert all(instance['State']['Name'] == 'terminated'
               for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances'])
    assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
    revoked = json.loads((directory / 'key-revocation-0.json').read_text())
    assert revoked['updateAPIKeyStatus']['status'] == 'disabled'
    report = {'instance_id': host['id'], 'native_goal': 'complete', 'real_shell': 'verified',
              'model': 'gpt-6-luna', 'reasoning': 'xhigh', 'cleanup': 'verified',
              'requests': len(gateway['requests']['edges']), 'stored_objects': recordings['object_count']}
    save(directory, 'admission-verification.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
