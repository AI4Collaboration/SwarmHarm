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
    source = args.source
    goals = json.loads((source / 'preflight-1-native-goals.json').read_text())[0]['rows']
    assert len(goals) == 1 and goals[0]['status'] == 'complete'
    root = source / 'preflight-1/raw/var/lib/peer-operator'
    sha = (root / 'codex.sha256').read_text().split()[0]
    assert sha == '12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad'
    shell = (source / 'preflight-1/raw/home/agent/shell-admission.txt').read_text()
    assert 'uid=1001(agent)' in shell
    gateway = json.loads((source / 'preflight-1-gateway.json').read_text())
    requests = [edge['node'] for edge in gateway['requests']['edges']]
    assert requests and all(request['modelID'] == 'gpt-6-luna' and request['reasoningEffort'] == 'xhigh' for request in requests)
    assert all(execution['node']['upstreamModelID'] == 'gpt-6-luna'
               for request in requests for execution in request['executions']['edges'])
    args.output.mkdir(parents=True, exist_ok=False)
    names = ['preflight-1-native-goals.json', 'preflight-1-gateway.json',
             'preflight-1-key-revocation.json', 'permission-probes.json', 'quota-probe.json',
             'token-quota-probe.json', 'preflight-quota-readback.json', 'preflight-token-quota-readback.json']
    for repeat in (1, 2):
        path = source / f'preflight-{repeat}/cleanup.json'
        cleanup = json.loads(path.read_text())
        assert all(instance['State']['Name'] == 'terminated'
                   for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances'])
        assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
        shutil.copyfile(path, args.output / f'preflight-{repeat}-cleanup.json')
    for name in names:
        shutil.copyfile(source / name, args.output / name)
    shutil.copyfile(root / 'codex.sha256', args.output / 'codex.sha256')
    shutil.copyfile(source / 'preflight-1/raw/home/agent/shell-admission.txt', args.output / 'shell-admission.txt')
    receipt = {'source_issue': 'SWH-78', 'harness': '100470a2', 'native_goal': 'complete',
               'codex_version': '0.160.0', 'codex_sha256': sha, 'model': 'gpt-6-luna', 'reasoning': 'xhigh',
               'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in args.output.iterdir()}}
    (args.output / 'reuse-verification.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
