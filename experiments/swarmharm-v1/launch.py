"""Launch one prepared collector independently of the chat-tool process group."""
import argparse
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
AXONHUB_API_BASE='https://lmportal.iefbr14.xyz/v1'
AXONHUB_LIVE_HARNESS_BASES={'pi-sdk':AXONHUB_API_BASE}
spec=importlib.util.spec_from_file_location('launch_atomic_reader',REPO/'experiments/runtime/atomic.py');infra=importlib.util.module_from_spec(spec);spec.loader.exec_module(infra)
guardrail_spec=importlib.util.spec_from_file_location(
    'launch_guardrails',REPO/'experiments/runtime/guardrails.py')
guardrails=importlib.util.module_from_spec(guardrail_spec);guardrail_spec.loader.exec_module(guardrails)
claude_spec=importlib.util.spec_from_file_location('launch_claude_policy',REPO/'experiments/runtime/claude_agent.py')
claude_policy=importlib.util.module_from_spec(claude_spec);claude_spec.loader.exec_module(claude_policy)


def collector_python():
    runtime=Path(os.environ.get('SWARMHARM_HARBOR_ENV',
                                REPO.parent/'eval-readiness/harbor-0.24.0')).expanduser().resolve()
    candidate=runtime/'bin/python'
    if not candidate.is_file():
        raise RuntimeError('Pinned Harbor 0.24.0 runtime is missing')
    executable=str(candidate)
    check=subprocess.run([executable,'-c',
        'from importlib.metadata import version; from harbor.models.task.config import TaskConfig; '
        'raise SystemExit(0 if version("harbor")=="0.24.0" else 1)'],
        capture_output=True,text=True,timeout=20)
    if check.returncode!=0:raise RuntimeError('Collector runtime must provide exact Harbor 0.24.0')
    return executable

def collector_command(root,registration_dir,key_file=None):
    argv=[collector_python(),str(HERE/'run.py'),'--phase','collect','--output',str(Path(root).resolve()),
          '--registration-dir',str(Path(registration_dir).resolve())]
    if key_file is not None:argv.extend(['--key-file',str(Path(key_file).resolve())])
    return argv

def wait_for_start(child, root, timeout_seconds=30):
    """Confirm the child's freeze checks before callers update progress docs."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        if (root / 'started.json').is_file():
            return
        code = child.poll()
        if code is not None:
            raise RuntimeError(
                f'Collector exited before start confirmation (exit {code}); '
                f'preserve {root / "controller.log"}. No replacement launch.')
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f'Collector {child.pid} has not confirmed startup; inspect '
                f'{root} before changing the worktree or starting anything else.')
        time.sleep(0.05)

def launch(output, registration_dir, *, key_file=None, command=None):
    root=guardrails.outside_repository(output,REPO,'Raw output directory')
    reg=json.loads((root/'registration.json').read_text())
    harness_kind=reg.get('harness',{}).get('kind')
    if reg.get('subscription_study') is True:
        if (harness_kind != 'claude-code' or reg.get('inference_gateway') != 'claude-subscription'
                or reg.get('live_collection_permitted') is not True
                or not claude_policy.selected_study_model(reg.get('models')) or reg.get('reasoning') != 'medium'):
            raise RuntimeError('Subscription study differs from explicit selection')
        if key_file is not None:
            raise ValueError('Subscription study accepts no API key')
    else:
        expected_base=AXONHUB_LIVE_HARNESS_BASES.get(harness_kind)
        if expected_base is None:
            raise RuntimeError(f'{harness_kind} does not yet have a registered AxonHub transport; an explicit subscription study is required.')
        if reg.get('live_collection_permitted', True) is not True:
            raise RuntimeError('This registration is not permitted for live collection.')
        if reg.get('inference_gateway','axonhub') != 'axonhub':
            raise RuntimeError('The registered gateway differs')
        if str(reg.get('api_base','')).rstrip('/') != expected_base:
            raise RuntimeError('All live rollouts must use the registered AxonHub API base.')
        if command is None:
            key_file=guardrails.credential_file(key_file,REPO)
    seal=json.loads((root/'registration-seal.json').read_text())
    if sha256((root/'registration.json').read_bytes()).hexdigest()!=seal['sha256']:
        raise RuntimeError('Registration differs.')
    for path,digest in reg['code_hashes'].items():
        if sha256((REPO/path).read_bytes()).hexdigest()!=digest:
            raise RuntimeError(f'Live source differs: {path}')
        if sha256((root/'code'/path).read_bytes()).hexdigest()!=digest:
            raise RuntimeError(f'Prepared source copy differs: {path}')
    with (root/'.launch.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'started.json').exists() or (root/'launcher.json').exists():
            raise RuntimeError('Use a new prepared world; never replace trajectories.')
        argv=command or collector_command(root,registration_dir,key_file)
        with (root/'controller.log').open('xb') as log:
            child=subprocess.Popen(argv,cwd=REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        infra.atomic_json(root/'launcher.json',{'at':infra.utc(),'pid':child.pid,'new_session':True,'scheduled_task':False,
                                             'same_prepared_collector':command is None,'registration_sha256':seal['sha256']})
        wait_for_start(child, root)
    return child.pid

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--registration-dir',type=Path,required=True)
    parser.add_argument('--key-file',type=Path,
        help='Required host-only AxonHub key for every live rollout.')
    a=parser.parse_args();print(json.dumps({'pid':launch(a.output,a.registration_dir,key_file=a.key_file),'scheduled_task':False}),flush=True)
