"""Run a newly registered trial; no retries or trajectory replacement."""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from harbor.trial.trial import Trial
from harbor.models.trial.config import TrialConfig
import agent

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

async def main(args):
    root = args.output.resolve()
    assert not root.exists(), 'Never overwrite output'
    agent.CAMPAIGN = root; agent.CONTROL = args.control
    if args.model == 'deepseek':
        agent.MODEL = 'deepseek-v4-pro'; agent.EFFORT = 'high'
        agent.transport = agent.mod('payment_deepseek', REPO / 'experiments/payables-v1/deepseek_transport.py')
        agent.transport.configure(agent.MODEL, 'https://lmportal.iefbr14.xyz/v1', key_file=args.key_file)
        if not args.control: agent.transport.key()
    else:
        agent.MODEL = 'gpt-5.6-sol'; agent.EFFORT = 'xhigh'
        agent.transport.configure(agent.MODEL, 'https://lmportal.iefbr14.xyz/v1', key_file=args.key_file)
    if not args.control:
        reg = json.loads((HERE / 'registration.json').read_text())
        for p, digest in reg['hashes'].items():
            assert hashlib.sha256((REPO / p).read_bytes()).hexdigest() == digest, p
        confirmation = json.loads((HERE / 'remote-confirmation.json').read_text())
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
        assert confirmation['commit'] == commit
        assert subprocess.check_output(['git', 'ls-remote', 'origin', 'refs/heads/main'], cwd=REPO, text=True).split()[0] == commit
        assert confirmation['registration_sha256'] == hashlib.sha256((HERE / 'registration.json').read_bytes()).hexdigest()
        image = subprocess.check_output(['docker', 'image', 'inspect', 'swarmharm-mimo-smoke:mcp-1.26.0', '--format', '{{.Id}}'], text=True).strip()
        assert image == reg['image']
    lock = (REPO.parent / 'eval-readiness/release-campaign-inference.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    root.mkdir(parents=True)
    agent.save(root / 'started.json', {'at': time.time(), 'pid': os.getpid(), 'control': args.control,
                                    'model': agent.MODEL, 'effort': agent.EFFORT})
    status = 'held'
    try:
        cfg = TrialConfig.model_validate({
            'task': {'path': str(REPO / 'tasks/mimo-payment/already-settled')},
            'trial_name': 'already-settled', 'trials_dir': str(root / 'trials'),
            'agent': {'import_path': 'agent:BusinessAgent', 'model_name': agent.MODEL},
            'environment': {'type': 'docker', 'delete': True}})
        trial = await Trial.create(cfg); result = await trial.run()
        agent.save(root / 'trial-result.json', result.model_dump(mode='json'))
        if result.exception_info: raise RuntimeError(str(result.exception_info))
        status = 'completed'
        print(json.dumps({'status': status, 'model': agent.MODEL, 'rewards': result.verifier_result.rewards}), flush=True)
    finally:
        agent.save(root / 'completion.json', {'at': time.time(), 'status': status, 'control': args.control,
                                           'model': agent.MODEL, 'no_retries': True})
        fcntl.flock(lock, fcntl.LOCK_UN); lock.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model', choices=['sol', 'deepseek'], default='sol')
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--control', action='store_true')
    asyncio.run(main(parser.parse_args()))
