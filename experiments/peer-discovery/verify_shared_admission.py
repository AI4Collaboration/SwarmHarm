import argparse
import hashlib
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    receipt = json.loads((args.source / 'reuse-verification.json').read_text())
    assert receipt['harness'] == '100470a2'
    assert receipt['codex_version'] == '0.160.0'
    assert receipt['model'] == 'gpt-6-luna' and receipt['reasoning'] == 'xhigh'
    args.output.mkdir(parents=True, exist_ok=False)
    for name, digest in receipt['files'].items():
        raw = (args.source / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        shutil.copyfile(args.source / name, args.output / name)
    goals = json.loads((args.output / 'preflight-1-native-goals.json').read_text())[0]['rows']
    assert len(goals) == 1 and goals[0]['status'] == 'complete'
    assert 'uid=1001(agent)' in (args.output / 'shell-admission.txt').read_text()
    metadata = json.loads((args.output / 'preflight-1-gateway.json').read_text())
    records = [edge['node'] for edge in metadata['requests']['edges']]
    assert records and all(record['modelID'] == 'gpt-6-luna' and record['reasoningEffort'] == 'xhigh'
                           for record in records)
    for repeat in (1, 2):
        cleanup = json.loads((args.output / f'preflight-{repeat}-cleanup.json').read_text())
        assert all(instance['State']['Name'] == 'terminated' for reservation in cleanup['instances']['Reservations']
                   for instance in reservation['Instances'])
        assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
    shutil.copyfile(args.source / 'reuse-verification.json', args.output / 'reuse-verification.json')
    print(json.dumps({'native_goal_and_shell': 'verified', 'hashed_files': len(receipt['files']),
                      'codex_version': receipt['codex_version'], 'model': receipt['model']}))


if __name__ == '__main__':
    main()
